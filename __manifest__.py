# -*- coding: utf-8 -*-
{
    'name': 'Actualizar Costo al Recibir Compra',
    'version': '18.0.4.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Actualiza el costo del producto con el último precio de compra al validar la recepción (método de costeo nativo).',
    'description': """
Actualizar Costo al Recibir Compra
==================================

Agrega un check **\"Actualizar costo al recibir compra\"** en las categorías de
producto. Cuando está activo (y la categoría usa el método de costeo nativo
**Precio Estándar**), al validar una recepción de compra el costo del
producto se actualiza con el precio unitario neto de esa recepción:

* Se aplican todos los descuentos de la línea de compra, incluidos los
  descuentos 2 y 3 de \`\`sp_purchase_multi_discount\`\` si está instalado.
* Se respeta la conversión de moneda, incluida la cotización manual del
  picking (\`\`stock_currency_valuation\`\`) si existe.
* El stock preexistente se revaloriza al nuevo costo (comportamiento nativo
  de Precio Estándar).

El método de costeo y la valoración son 100% nativos de Odoo.

Trazabilidad
------------

Cada cambio de costo se registra en el chatter de la plantilla del producto,
con el costo anterior, el nuevo, la variación porcentual y la recepción y
orden de compra que lo originaron.

Controles antes de confirmar la compra
--------------------------------------

Como el precio de la orden termina siendo el costo del producto, se controla
antes de confirmar:

* **Precio cero**: bloqueo duro. No se puede confirmar una orden con líneas a
  precio cero sobre productos que actualizan el costo al recibir.
* **Desvío excesivo**: si el precio neto se aparta del costo actual más que el
  porcentaje configurado en la categoría (campo *Desvío máximo de costo*), se
  muestra una advertencia con el detalle. Es confirmable, y la confirmación
  queda registrada en el chatter de la orden.

Costos en destino
-----------------

Los costos en destino nativos solo aceptan productos PEPS o Costo Promedio.
Con este módulo también se aplican a productos Precio Estándar de categorías
con el check activo. Al validar el costo en destino:

* Si la recepción es la última compra recibida del producto, el costo pasa a
  ser el precio neto de compra más todos los costos en destino validados de
  esa recepción, por unidad. El stock preexistente se revaloriza.
* Si ya hubo una recepción de compra posterior, el último costo no se pisa:
  el gasto se distribuye sobre el stock actual.

El cambio queda registrado en el chatter del producto.
""",
    'author': 'Aftermoves',
    'website': 'https://aftermoves.com',
    'license': 'LGPL-3',
    'depends': [
        'stock_account',
        'purchase_stock',
        'stock_landed_costs',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/product_category_views.xml',
        'views/purchase_cost_deviation_warning_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
