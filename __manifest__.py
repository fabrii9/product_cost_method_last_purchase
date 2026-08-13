# -*- coding: utf-8 -*-
{
    'name': 'Actualizar Costo al Recibir Compra',
    'version': '18.0.2.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Actualiza el costo del producto con el último precio de compra al validar la recepción (método de costeo nativo).',
    'description': """
Actualizar Costo al Recibir Compra
==================================

Agrega un check **"Actualizar costo al recibir compra"** en las categorías de
producto. Cuando está activo (y la categoría usa el método de costeo nativo
**Precio Estándar**), al validar una recepción de compra el costo del
producto se actualiza con el precio unitario neto de esa recepción:

* Se aplican todos los descuentos de la línea de compra, incluidos los
  descuentos 2 y 3 de ``sp_purchase_multi_discount`` si está instalado.
* Se respeta la conversión de moneda, incluida la cotización manual del
  picking (``stock_currency_valuation``) si existe.
* El stock preexistente se revaloriza al nuevo costo (comportamiento nativo
  de Precio Estándar).

El método de costeo y la valoración son 100% nativos de Odoo.
    """,
    'author': 'Aftermoves',
    'website': 'https://aftermoves.com',
    'license': 'LGPL-3',
    'depends': [
        'stock_account',
        'purchase_stock',
    ],
    'data': [
        'views/product_category_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
