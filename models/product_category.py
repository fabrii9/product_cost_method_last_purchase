# -*- coding: utf-8 -*-
"""
Extensión de product.category para agregar el método de costeo
'Último Precio de Compra'.
"""

from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

    property_cost_method = fields.Selection([
        ('standard', 'Standard Price'),
        ('fifo', 'First In First Out (FIFO)'),
        ('average', 'Average Cost (AVCO)'),
        ('last_purchase_price', 'Último Precio de Compra'),
    ], string="Costing Method",
        company_dependent=True, copy=True,
        help="""Standard Price: The products are valued at their standard cost defined on the product.
        Average Cost (AVCO): The products are valued at weighted average cost.
        First In First Out (FIFO): The products are valued supposing those that enter the company first will also leave it first.
        Último Precio de Compra: El costo del producto se actualiza automáticamente con el último precio pagado en una recepción de compra, sin realizar cálculos adicionales.
        """,
        tracking=True,
    )
