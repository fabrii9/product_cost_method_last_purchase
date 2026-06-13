# -*- coding: utf-8 -*-
"""
Extensión de stock.move para el método de costeo 'Último Precio de Compra'.
Cuando se recibe mercadería proveniente de una compra, el costo del producto
pasa a ser el precio unitario de la recepción, sin aplicar promedios ni FIFO.
"""

from odoo import models
from odoo.tools import float_is_zero


class StockMove(models.Model):
    _inherit = 'stock.move'

    def product_price_update_before_done(self, forced_qty=None):
        """Actualiza el costo estándar al último precio de compra.

        Para productos cuya categoría utiliza el método de costeo
        'last_purchase_price', el costo del producto se reemplaza por el
        precio unitario de la recepción sin realizar ningún cálculo adicional.
        """
        last_purchase_moves = self.filtered(
            lambda m: m.with_company(m.company_id).product_id.cost_method == 'last_purchase_price' and m._is_in()
        )
        other_moves = self - last_purchase_moves

        # Mantener el comportamiento estándar de Odoo para AVCO y otros métodos.
        super(StockMove, other_moves).product_price_update_before_done(forced_qty=forced_qty)

        for move in last_purchase_moves:
            move = move.with_company(move.company_id)
            product = move.product_id
            move_cost = move._get_price_unit()
            precision = move.env['decimal.precision'].precision_get('Product Price')

            if product.lot_valuated:
                for lot, unit_cost in move_cost.items():
                    if float_is_zero(unit_cost, precision_digits=precision):
                        continue
                    # Actualizar el costo del lote y del producto con el último precio.
                    if lot:
                        lot.with_company(move.company_id).with_context(disable_auto_svl=True).sudo().write({
                            'standard_price': unit_cost,
                        })
                    product.with_company(move.company_id).with_context(disable_auto_svl=True).sudo().write({
                        'standard_price': unit_cost,
                    })
            else:
                unit_cost = next(iter(move_cost.values()))
                if float_is_zero(unit_cost, precision_digits=precision):
                    continue
                product.with_company(move.company_id).with_context(disable_auto_svl=True).sudo().write({
                    'standard_price': unit_cost,
                })
