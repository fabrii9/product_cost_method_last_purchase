# -*- coding: utf-8 -*-
"""
Actualización del costo al recibir compras (método de costeo nativo).

Para productos de categorías con método de costeo Precio Estándar y el check
'Actualizar costo al recibir compra' activo, al validar una recepción de
compra el costo del producto se actualiza con el precio unitario neto de la
recepción (todos los descuentos aplicados). El resto del comportamiento de
valoración es 100% nativo de Odoo.

El cambio de costo queda registrado en el chatter del producto, indicando el
costo anterior, el nuevo, la variación y la recepción que lo originó: la
revalorización del stock preexistente es silenciosa en Odoo y sin esta traza
solo queda la capa de valoración para reconstruir qué pasó.
"""

from markupsafe import Markup

from odoo import models, _
from odoo.tools import float_is_zero, float_compare
from odoo.tools.misc import formatLang


class StockMove(models.Model):
    _inherit = 'stock.move'

    def product_price_update_before_done(self, forced_qty=None):
        """Actualiza el costo estándar al último precio de compra neto.

        Solo para recepciones de productos cuya categoría usa Precio Estándar
        y tiene activo el check 'Actualizar costo al recibir compra'. El
        write del costo se hace SIN disable_auto_svl para que el core genere
        la capa de revalorización del stock preexistente (comportamiento
        nativo de Precio Estándar).
        """
        update_moves = self.filtered(
            lambda m: m.with_company(m.company_id).product_id.cost_method == 'standard'
            and m.with_company(m.company_id).product_id.categ_id.update_cost_on_receipt
            and m._is_in()
        )
        other_moves = self - update_moves

        # Mantener el comportamiento estándar de Odoo para el resto.
        super(StockMove, other_moves).product_price_update_before_done(forced_qty=forced_qty)

        for move in update_moves:
            move = move.with_company(move.company_id)
            product = move.product_id
            move_cost = move._get_last_purchase_price_unit()
            precision = move.env['decimal.precision'].precision_get('Product Price')

            if product.lot_valuated:
                for lot, unit_cost in move_cost.items():
                    if float_is_zero(unit_cost, precision_digits=precision):
                        continue
                    if lot:
                        lot.with_company(move.company_id).sudo().write({
                            'standard_price': unit_cost,
                        })
                    old_cost = product.with_company(move.company_id).standard_price
                    product.with_company(move.company_id).sudo().write({
                        'standard_price': unit_cost,
                    })
                    move._log_cost_update(product, old_cost, unit_cost, lot=lot)
            else:
                unit_cost = next(iter(move_cost.values()))
                if float_is_zero(unit_cost, precision_digits=precision):
                    continue
                old_cost = product.with_company(move.company_id).standard_price
                product.with_company(move.company_id).sudo().write({
                    'standard_price': unit_cost,
                })
                move._log_cost_update(product, old_cost, unit_cost)

    def _log_cost_update(self, product, old_cost, new_cost, lot=None):
        """Deja constancia del cambio de costo en el chatter del producto.

        Se postea sobre la plantilla (es donde el usuario mira el historial) y
        solo si el costo efectivamente cambió, para no ensuciar el chatter con
        recepciones que reconfirman el mismo precio.
        """
        self.ensure_one()
        precision = self.env['decimal.precision'].precision_get('Product Price')
        if float_compare(old_cost, new_cost, precision_digits=precision) == 0:
            return

        currency = self.company_id.currency_id
        variation = ''
        if not float_is_zero(old_cost, precision_digits=precision):
            pct = (new_cost - old_cost) / old_cost * 100.0
            variation = ' (%s%s %%)' % ('+' if pct >= 0 else '', round(pct, 2))

        origin = self.picking_id.name or self.reference or ''
        purchase = self.purchase_line_id.order_id

        # formatLang devuelve HTML (usa &nbsp; como separador), por eso los
        # importes se envuelven en Markup: de lo contrario el escapado los
        # mostraría literales en el chatter.
        headline = _(
            'Costo actualizado por recepción de compra: %(old)s → %(new)s%(variation)s',
            old=Markup(formatLang(self.env, old_cost, currency_obj=currency)),
            new=Markup(formatLang(self.env, new_cost, currency_obj=currency)),
            variation=variation,
        )
        details = []
        if origin:
            details.append(_('Recepción: %s', origin))
        if purchase:
            details.append(_('Orden de compra: %s', purchase.name))
        if lot:
            details.append(_('Lote: %s', lot.name))

        # El chatter interpreta HTML: se arma con Markup para que los saltos de
        # línea y el formato de moneda se vean correctamente.
        body = Markup('<p>') + headline + Markup('</p>')
        if details:
            body += Markup('<ul>%s</ul>') % Markup('').join(
                Markup('<li>%s</li>') % d for d in details
            )

        product.product_tmpl_id.sudo().message_post(body=body)

    def _get_last_purchase_price_unit(self):
        """Precio unitario de la recepción con TODOS los descuentos aplicados.

        ``sp_purchase_multi_discount`` / ``purchase_global_discount`` agregan
        los campos ``discount2`` y ``discount3`` a las líneas de compra, pero
        el ``_get_price_unit`` estándar puede ignorarlos (p. ej. cuando se
        factura antes de recibir, el core solo usa el descuento nativo de la
        factura) o incluso ignorar el descuento nativo (``stock_currency_valuation``
        usa el ``price_unit`` bruto cuando el picking tiene cotización manual).
        Por eso el costo se calcula directamente desde el precio neto de la
        línea de compra.

        Devuelve el mismo formato que ``_get_price_unit``: un dict
        {stock.lot: precio} (con el lote vacío si el producto no se valúa por lote).
        """
        self.ensure_one()
        line = self.purchase_line_id
        if self._should_ignore_pol_price():
            return self._get_price_unit()
        order = line.order_id
        # _get_gross_price_unit aplica los descuentos secuenciales (nativo +
        # discount2/discount3 si sp_purchase_multi_discount está instalado),
        # quita los impuestos incluidos y convierte a la UdM del producto.
        price_unit = line._get_gross_price_unit()
        if order.currency_id != order.company_id.currency_id:
            picking = self.picking_id
            currency_rate = getattr(picking, 'currency_rate', 0.0) or 0.0
            valuation_currency = getattr(picking, 'valuation_currency_id', self.env['res.currency'])
            if currency_rate and order.currency_id == valuation_currency:
                # Cotización manual cargada en el picking (stock_currency_valuation).
                price_unit = price_unit / currency_rate
            else:
                convert_date = self._get_currency_convert_date()
                price_unit = order.currency_id._convert(
                    price_unit, order.company_id.currency_id, order.company_id, convert_date, round=False)
        if self.product_id.lot_valuated:
            return dict.fromkeys(self.lot_ids, price_unit)
        return {self.env['stock.lot']: price_unit}
