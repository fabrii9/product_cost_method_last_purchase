# -*- coding: utf-8 -*-
"""
Wizard de advertencia por desvío de costo.

No es un paso administrativo: es el punto donde alguien se hace cargo de que
el precio cargado va a convertirse en el costo del producto y a revalorizar
el stock. Por eso la confirmación queda registrada en el chatter de la orden.
"""

from odoo import fields, models, _


class PurchaseCostDeviationWarning(models.TransientModel):
    _name = 'purchase.cost.deviation.warning'
    _description = 'Advertencia por desvío entre precio de compra y costo'

    order_ids = fields.Many2many(
        comodel_name='purchase.order',
        string='Órdenes de Compra',
        required=True,
    )
    message = fields.Text(
        string='Detalle',
        readonly=True,
    )

    def action_confirm(self):
        """Confirma las órdenes salteando el control de desvío."""
        self.ensure_one()
        self.order_ids._log_cost_deviation_confirmation(self.message)
        return self.order_ids.with_context(
            skip_cost_deviation_check=True
        ).button_confirm()

    def action_review(self):
        """Vuelve a la orden sin confirmar, para corregir los precios."""
        self.ensure_one()
        return {'type': 'ir.actions.act_window_close'}
