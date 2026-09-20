# -*- coding: utf-8 -*-
"""
Controles sobre el precio de compra antes de confirmar la orden.

Como el costo del producto se actualiza automáticamente al validar la
recepción (ver ``stock_move.py``), un precio mal cargado en la orden de
compra no se queda en la orden: se propaga al costo del producto, revaloriza
todo el stock preexistente e impacta en los asientos contables. Los dos
controles de este archivo atacan el problema en el único momento en que
todavía es barato corregirlo: antes de confirmar.

1. Precio cero: bloqueo duro (``UserError``). No se puede confirmar.
2. Desvío excesivo: advertencia confirmable, a través de un wizard que
   explica el desvío y exige una confirmación explícita.
"""

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero
from odoo.tools.misc import formatLang


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def button_confirm(self):
        # El bloqueo por precio cero es incondicional: no hay forma de
        # confirmar una orden con costo cero sobre productos que valorizan.
        self._check_zero_price_lines()

        # El aviso de desvío es confirmable. Al volver desde el wizard, el
        # contexto trae la marca y se saltea el control.
        if not self.env.context.get('skip_cost_deviation_check'):
            deviations = self._get_cost_deviation_lines()
            if deviations:
                return self._open_cost_deviation_wizard(deviations)

        return super().button_confirm()

    # -------------------------------------------------------------------------
    # 1. Precio cero: bloqueo duro
    # -------------------------------------------------------------------------

    def _check_zero_price_lines(self):
        """Impide confirmar una orden con líneas a precio cero.

        Solo se controlan las líneas de productos que actualizan el costo al
        recibir: en el resto, un precio cero puede ser legítimo (bonificación,
        muestra sin valor) y no tiene consecuencias sobre la valoración.
        """
        precision = self.env['decimal.precision'].precision_get('Product Price')
        for order in self:
            if order.state not in ('draft', 'sent'):
                continue
            zero_lines = order.order_line.filtered(
                lambda l: not l.display_type
                and l._updates_cost_on_receipt()
                and float_is_zero(l._get_net_cost_price_unit(), precision_digits=precision)
            )
            if not zero_lines:
                continue

            detail = '\n'.join(
                '  • %s' % line.product_id.display_name for line in zero_lines
            )
            raise UserError(_(
                'No se puede confirmar la orden %(order)s: hay líneas con precio cero.\n\n'
                '%(detail)s\n\n'
                '¿Por qué se bloquea?\n'
                'Estos productos actualizan su costo al validar la recepción. Si la '
                'orden se confirma con precio cero, al recibir la mercadería el costo '
                'del producto pasa a cero, TODO el stock existente de ese producto se '
                'revaloriza a cero y se genera el asiento contable correspondiente. '
                'El margen de venta queda destruido y revertirlo exige ajustes '
                'manuales de inventario y de contabilidad.\n\n'
                'Cómo resolverlo:\n'
                '  • Cargá el precio de compra real en la línea; o\n'
                '  • si la mercadería es sin cargo, cargá el precio de lista y '
                'aplicá un descuento del 100%%, de modo que el costo quede correcto; o\n'
                '  • usá un producto de una categoría que no tenga activo '
                '"Actualizar costo al recibir compra".',
                order=order.name,
                detail=detail,
            ))

    # -------------------------------------------------------------------------
    # 2. Desvío respecto del costo actual: advertencia confirmable
    # -------------------------------------------------------------------------

    def _get_cost_deviation_lines(self):
        """Devuelve las líneas cuyo precio se aparta del costo más que el umbral.

        El umbral se configura por categoría (``cost_deviation_alert_pct``);
        en cero, la categoría no se controla.
        """
        precision = self.env['decimal.precision'].precision_get('Product Price')
        deviations = []
        for order in self:
            if order.state not in ('draft', 'sent'):
                continue
            for line in order.order_line:
                if line.display_type or not line._updates_cost_on_receipt():
                    continue
                threshold = line.product_id.categ_id.cost_deviation_alert_pct
                if threshold <= 0:
                    continue
                current_cost = line.product_id.with_company(order.company_id).standard_price
                if float_is_zero(current_cost, precision_digits=precision):
                    # Sin costo previo no hay desvío que medir: la primera
                    # compra del producto siempre define el costo.
                    continue
                new_cost = line._get_net_cost_price_unit_company_currency()
                if float_is_zero(new_cost, precision_digits=precision):
                    # El precio cero ya se bloqueó antes.
                    continue
                pct = (new_cost - current_cost) / current_cost * 100.0
                if abs(pct) > threshold:
                    deviations.append({
                        'line': line,
                        'current_cost': current_cost,
                        'new_cost': new_cost,
                        'pct': pct,
                        'threshold': threshold,
                    })
        return deviations

    def _open_cost_deviation_wizard(self, deviations):
        """Abre el wizard de advertencia con el detalle del desvío."""
        currency = self.env.company.currency_id
        detail = '\n'.join(
            '  • %s: costo actual %s → precio de compra %s   (%s%s %%, umbral %s %%)' % (
                d['line'].product_id.display_name,
                formatLang(self.env, d['current_cost'], currency_obj=currency),
                formatLang(self.env, d['new_cost'], currency_obj=currency),
                '+' if d['pct'] >= 0 else '',
                round(d['pct'], 2),
                round(d['threshold'], 2),
            )
            for d in deviations
        )
        message = _(
            'El precio de compra se desvía del costo actual en %(count)s línea(s):\n\n'
            '%(detail)s\n\n'
            '¿Por qué importa?\n'
            'Al validar la recepción, estos precios pasan a ser el costo del producto '
            'y todo el stock existente se revaloriza, generando asientos contables. '
            'Un desvío grande suele indicar un error de carga: precio con o sin IVA, '
            'unidad de medida equivocada (caja en vez de unidad), o un cero de más.\n\n'
            'Revisá el precio y la unidad de medida. Si los valores son correctos, '
            'confirmá para continuar.',
            count=len(deviations),
            detail=detail,
        )
        wizard = self.env['purchase.cost.deviation.warning'].create({
            'order_ids': [(6, 0, self.ids)],
            'message': message,
        })
        return {
            'name': _('Revisar precios de compra'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.cost.deviation.warning',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _log_cost_deviation_confirmation(self, message):
        """Registra en el chatter que el desvío fue confirmado y por quién."""
        for order in self:
            order.message_post(body=_(
                'Orden confirmada con desvío de costo aceptado por %(user)s.\n\n%(message)s',
                user=self.env.user.display_name,
                message=message,
            ))


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _updates_cost_on_receipt(self):
        """True si esta línea va a actualizar el costo del producto al recibir.

        Replica la condición de ``StockMove.product_price_update_before_done``
        para que el control previo y el efecto real no puedan divergir.
        """
        self.ensure_one()
        product = self.product_id
        if not product:
            return False
        company = self.order_id.company_id or self.env.company
        product = product.with_company(company)
        return (
            product.cost_method == 'standard'
            and product.categ_id.update_cost_on_receipt
        )

    def _get_net_cost_price_unit(self):
        """Precio neto de la línea, en la moneda de la orden.

        Usa el mismo ``_get_gross_price_unit`` que emplea el módulo al recibir,
        de modo que incluye los descuentos múltiples de
        ``sp_purchase_multi_discount`` y la conversión de unidad de medida.
        """
        self.ensure_one()
        if not self.product_id:
            return 0.0
        return self._get_gross_price_unit()

    def _get_net_cost_price_unit_company_currency(self):
        """Precio neto convertido a la moneda de la compañía.

        Es el valor que terminará escrito como ``standard_price``, así que es
        el único comparable contra el costo actual del producto.
        """
        self.ensure_one()
        price_unit = self._get_net_cost_price_unit()
        order = self.order_id
        company = order.company_id or self.env.company
        if order.currency_id and order.currency_id != company.currency_id:
            convert_date = order.date_approve or order.date_order or fields.Datetime.now()
            price_unit = order.currency_id._convert(
                price_unit, company.currency_id, company, convert_date, round=False)
        return price_unit
