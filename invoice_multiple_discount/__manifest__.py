##############################################################################
#
#    Copyright (C) 2019  jeo Software  (http://www.jeosoft.com.ar)
#    All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'Multiple discounts on invoices',
    'version': '13.0.0.0.3',
    'category': 'Tools',
    'summary': "Add three discount columns in invoices",
    'author': "jeo Software",
    'website': 'http://github.com/jobiols/odoo-addons',
    'license': 'AGPL-3',
    'depends': [
        'account',
        'report_aeroo'
    ],
    'data': [
        'views/account_invoice.xml',
        'views/invoice_report.xml',
        'views/partner_view.xml'
    ],
    'demo': [
    ],
    'installable': False,
    'auto_install': False,
    'application': False,
}