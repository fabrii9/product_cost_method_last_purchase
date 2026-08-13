# -*- coding: utf-8 -*-
"""
Extensión de product.category: check 'Actualizar costo al recibir compra'.

No agrega métodos de costeo nuevos: la categoría usa el nativo Precio
Estándar. El check habilita que, al validar una recepción de compra, el
costo del producto se actualice con el precio unitario neto de la recepción.
"""

from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    update_cost_on_receipt = fields.Boolean(
        string='Actualizar costo al recibir compra',
        copy=True,
        tracking=True,
        help="Solo aplica con el método de costeo Precio Estándar. Si está "
             "activo, al validar una recepción de compra el costo del "
             "producto se actualiza con el precio unitario neto de esa "
             "recepción (con todos los descuentos aplicados) y el stock "
             "preexistente se revaloriza al nuevo costo.",
    )
