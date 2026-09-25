# -*- coding: utf-8 -*-
"""
Costos en destino sobre productos con Precio Estándar.

El core de ``stock_landed_costs`` solo acepta productos PEPS o Costo Promedio:
``get_valuation_lines`` descarta el resto y ``button_validate`` solo actualiza
el costo de esos dos métodos. Este archivo habilita también los productos de
categorías con Precio Estándar y el check 'Actualizar costo al recibir compra'.

La capa de valoración y el asiento del costo en destino los genera el core sin
cambios (esa parte no depende del método de costeo). Lo que se agrega es la
actualización del costo del producto después de validar:

* Si la recepción es la última compra recibida del producto, el costo pasa a
  ser el precio neto de compra más todos los costos en destino validados sobre
  esa recepción, por unidad. Es el mismo criterio del módulo ("último costo de
  compra"), ahora puesto en depósito.
* Si ya hubo una recepción de compra posterior, el último costo no se pisa: el
  gasto se distribuye sobre el stock actual (valor / cantidad).

En ambos casos el write del costo se hace SIN ``disable_auto_svl``. En Precio
Estándar la revalorización nativa vale ``nuevo_precio * cantidad - valor``, y
como el core ya sumó el costo en destino al valor, solo se revaloriza la
diferencia: nada se cuenta dos veces.
"""

from collections import defaultdict

from markupsafe import Markup

from odoo import models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero, float_compare
from odoo.tools.misc import formatLang


class StockLandedCost(models.Model):
    _inherit = 'stock.landed.cost'

    def get_valuation_lines(self):
        """Reescribe el core para aceptar Precio Estándar con el check activo.

        Es la misma lógica del core; solo cambia la condición de elegibilidad
        (ver ``StockMove._is_landed_cost_eligible``).
        """
        self.ensure_one()
        lines = []

        for move in self._get_targeted_move_ids():
            if not move._is_landed_cost_eligible() or move.state == 'cancel' or not move.quantity:
                continue
            qty = move.product_uom._compute_quantity(move.quantity, move.product_id.uom_id)
            vals = {
                'product_id': move.product_id.id,
                'move_id': move.id,
                'quantity': qty,
                'former_cost': sum(move._get_stock_valuation_layer_ids().mapped('value')),
                'weight': move.product_id.weight * qty,
                'volume': move.product_id.volume * qty
            }
            lines.append(vals)

        if not lines:
            target_model_descriptions = dict(self._fields['target_model']._description_selection(self.env))
            raise UserError(_(
                'No se pueden aplicar costos en destino sobre el/la %s seleccionado/a. '
                'Solo se aplican a productos con método de costeo PEPS o Costo '
                'Promedio, o Precio Estándar con "Actualizar costo al recibir compra" '
                'activo en la categoría.',
                target_model_descriptions[self.target_model]))
        return lines

    def button_validate(self):
        res = super().button_validate()
        for cost in self:
            cost.with_company(cost.company_id)._update_standard_cost_from_landed_cost()
        return res

    def _update_standard_cost_from_landed_cost(self):
        """Actualiza el costo de los productos Precio Estándar del costo en destino."""
        self.ensure_one()
        adjustment_lines = self.valuation_adjustment_lines.filtered(
            lambda l: l.move_id and l.move_id._updates_standard_cost_on_landed_cost()
        )
        if not adjustment_lines:
            return

        # Un producto puede venir en varias recepciones del mismo costo en
        # destino: el costo se calcula una sola vez, con el movimiento más
        # reciente.
        moves_by_product = defaultdict(lambda: self.env['stock.move'])
        for move in adjustment_lines.move_id:
            moves_by_product[move.product_id] |= move

        for product, moves in moves_by_product.items():
            product = product.with_company(self.company_id)
            move = moves.sorted(lambda m: (m.date, m.id))[-1]
            if product.lot_valuated:
                self._update_lot_standard_cost(product, move)
            else:
                self._update_product_standard_cost(product, move)

    def _update_product_standard_cost(self, product, move):
        precision = self.env['decimal.precision'].precision_get('Product Price')
        if float_compare(product.quantity_svl, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
            return

        if move._is_last_purchase_receipt():
            purchase_price = next(iter(move._get_last_purchase_price_unit().values()))
            new_cost = purchase_price + move._get_landed_cost_per_unit()
        else:
            new_cost = product.value_svl / product.quantity_svl

        if float_is_zero(new_cost, precision_digits=precision):
            return
        old_cost = product.standard_price
        product.sudo().write({'standard_price': new_cost})
        self._log_landed_cost_update(product, move, old_cost, new_cost)

    def _update_lot_standard_cost(self, product, move):
        precision = self.env['decimal.precision'].precision_get('Product Price')
        is_last = move._is_last_purchase_receipt()
        landed_per_unit = move._get_landed_cost_per_unit() if is_last else 0.0
        purchase_prices = move._get_last_purchase_price_unit() if is_last else {}

        for lot in move.lot_ids.with_company(self.company_id):
            if float_compare(lot.quantity_svl, 0.0, precision_rounding=product.uom_id.rounding) <= 0:
                continue
            if is_last:
                new_cost = purchase_prices.get(lot, 0.0) + landed_per_unit
            else:
                new_cost = lot.value_svl / lot.quantity_svl
            if float_is_zero(new_cost, precision_digits=precision):
                continue
            old_cost = lot.standard_price
            lot.sudo().write({'standard_price': new_cost})
            if is_last:
                # Mismo criterio que la recepción: el costo del producto
                # acompaña al del último lote comprado.
                product.sudo().write({'standard_price': new_cost})
            self._log_landed_cost_update(product, move, old_cost, new_cost, lot=lot)

    def _log_landed_cost_update(self, product, move, old_cost, new_cost, lot=None):
        """Deja constancia en el chatter del producto, igual que la recepción."""
        precision = self.env['decimal.precision'].precision_get('Product Price')
        if float_compare(old_cost, new_cost, precision_digits=precision) == 0:
            return

        currency = self.company_id.currency_id
        variation = ''
        if not float_is_zero(old_cost, precision_digits=precision):
            pct = (new_cost - old_cost) / old_cost * 100.0
            variation = ' (%s%s %%)' % ('+' if pct >= 0 else '', round(pct, 2))

        headline = _(
            'Costo actualizado por costo en destino: %(old)s → %(new)s%(variation)s',
            old=Markup(formatLang(self.env, old_cost, currency_obj=currency)),
            new=Markup(formatLang(self.env, new_cost, currency_obj=currency)),
            variation=variation,
        )
        details = [_('Costo en destino: %s', self.name)]
        if move.picking_id:
            details.append(_('Recepción: %s', move.picking_id.name))
        if move.purchase_line_id:
            details.append(_('Orden de compra: %s', move.purchase_line_id.order_id.name))
        if lot:
            details.append(_('Lote: %s', lot.name))
        if not move._is_last_purchase_receipt():
            details.append(_(
                'Hay recepciones de compra posteriores: el gasto se distribuyó '
                'sobre el stock actual sin reemplazar el último costo.'))

        body = Markup('<p>') + headline + Markup('</p>')
        body += Markup('<ul>%s</ul>') % Markup('').join(
            Markup('<li>%s</li>') % d for d in details
        )
        product.product_tmpl_id.sudo().message_post(body=body)


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _updates_standard_cost_on_landed_cost(self):
        """True si el producto es Precio Estándar con el check de la categoría."""
        self.ensure_one()
        product = self.with_company(self.company_id).product_id
        return product.cost_method == 'standard' and product.categ_id.update_cost_on_receipt

    def _is_landed_cost_eligible(self):
        self.ensure_one()
        product = self.with_company(self.company_id).product_id
        return product.cost_method in ('fifo', 'average') or self._updates_standard_cost_on_landed_cost()

    def _is_last_purchase_receipt(self):
        """True si no hay recepciones de compra posteriores de este producto.

        Solo las recepciones de compra actualizan el costo (ver
        ``product_price_update_before_done``), por eso son las únicas que
        cuentan para decidir si este movimiento define el último costo.
        """
        self.ensure_one()
        if not self.purchase_line_id or not self._is_in():
            return False
        later_moves = self.search([
            ('id', '!=', self.id),
            ('product_id', '=', self.product_id.id),
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('purchase_line_id', '!=', False),
            '|', ('date', '>', self.date),
                 '&', ('date', '=', self.date), ('id', '>', self.id),
        ])
        return not any(m._is_in() for m in later_moves)

    def _get_landed_cost_per_unit(self):
        """Suma de todos los costos en destino validados del movimiento, por unidad.

        Se suman todos (no solo el que se está validando) para que cargar el
        flete y la aduana en costos en destino separados dé el mismo costo que
        cargarlos juntos. Incluye los costos en destino negativos (reversiones).
        """
        self.ensure_one()
        qty = self.product_uom._compute_quantity(self.quantity, self.product_id.uom_id)
        if float_is_zero(qty, precision_rounding=self.product_id.uom_id.rounding):
            return 0.0
        adjustment_lines = self.env['stock.valuation.adjustment.lines'].search([
            ('move_id', '=', self.id),
            ('cost_id.state', '=', 'done'),
        ])
        return sum(adjustment_lines.mapped('additional_landed_cost')) / qty
