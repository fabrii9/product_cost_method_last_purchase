# -*- coding: utf-8 -*-
{
    'name': 'Método de Costeo - Último Precio de Compra',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Agrega el método de costeo "Último Precio de Compra" a las categorías de producto.',
    'description': """
Método de Costeo - Último Precio de Compra
===========================================

Este módulo agrega un nuevo método de costeo en las categorías de producto:
**Último Precio de Compra**.

Funcionamiento:
* Al recibir mercadería proveniente de una compra, el costo del producto se
  actualiza automáticamente con el precio unitario de esa recepción.
* No se realizan cálculos de promedio ponderado (AVCO) ni FIFO.
* Las salidas de stock usan el último costo registrado.

Requiere que los productos tengan activada la valoración de inventario
(manual o automática).
    """,
    'author': 'Aftermoves',
    'website': 'https://aftermoves.com',
    'license': 'LGPL-3',
    'depends': [
        'stock_account',
        'purchase_stock',
    ],
    'data': [],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
