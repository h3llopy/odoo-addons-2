# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging

_logger = logging.getLogger(__name__)

from openerp import api, models, fields
from mappers import ProductMapper, SectionMapper, ItemMapper, FamilyMapper, \
    ProductCodeMapper
import csv
from openerp.addons.base.ir.ir_mail_server import MailDeliveryException
from time import time
from datetime import timedelta


class ProductProduct(models.Model):
    _inherit = "product.template"

    upv = fields.Integer(
        help='Agrupacion mayorista'
    )

    item_id = fields.Many2one(
        'product_autoload.item'
    )

    productcode_ids = fields.One2many(
        'product_autoload.productcode',
        'product_id',
        help="All barcodes belonging to this product"
    )

    item_code = fields.Char(
        help="Code from bulonfer, not shown"
    )

    default_item_code = fields.Char(
        help="Code from bulonfer, extracted from default_code",
        calculated='_get_default_item_code'
    )

    wholesaler_bulk = fields.Integer(

    )

    retail_bulk = fields.Integer(

    )

    @api.one
    @api.depends('default_code')
    def _get_default_item_code(self):
        return self.default_code.split('.')[0]

    @api.multi
    def process_file(self, file_path, file, class_mapper, vendor=False,
                     supplierinfo=False):
        """ Procesa un archivo csv con un mapper
        """

        try:
            with open(file_path + file, 'r') as file_csv:
                reader = csv.reader(file_csv)
                for line in reader:
                    if line:
                        prod = class_mapper(line, file_path, vendor,
                                            supplierinfo)
                        prod.execute(self.env)
        except IOError as ex:
            _logger.error('%s %s', ex.filename, ex.strerror)

    @api.model
    def category_load(self, file_path):
        """ Carga las tablas auxiliares por unica vez, o cuando haga falta
        """
        item_obj = self.env['product_autoload.item']
        item_obj.unlink_data()
        self.process_file(file_path, 'section.csv', SectionMapper)
        self.process_file(file_path, 'family.csv', FamilyMapper)
        self.process_file(file_path, 'item.csv', ItemMapper)
        self.process_file(file_path, 'productcode.csv', ProductCodeMapper)
        item_obj.link_data()
        item_obj.create_categories()

    @api.model
    def auto_load(self, file_path):
        """ Carga todos los productos que tienen timestamp > ultima carga
        """
        self.send_email('Replicacion Bulonfer, Inicio', 'Se inicio el proceso')
        start_time = time()

        bulonfer = self.env['res.partner'].search(
            [('name', 'like', 'Bulonfer')])
        if not bulonfer:
            raise Exception('Vendor Bulonfer not found')

        supplierinfo = self.env['product.supplierinfo']

        try:
            self.process_file(file_path, 'data.csv', ProductMapper,
                              vendor=bulonfer, supplierinfo=supplierinfo)
            self.category_load(file_path)
            elapsed_time = time() - start_time
            self.send_email('Replicacion Bulonfer, Fin', 'Termino el proceso',
                            elapsed_time)

        except Exception as ex:
            _logger.error('Falla del proceso---------------------')
            self.send_email('Replicacion Bulonfer ERROR', ex.message)
            raise Exception('=== Falla del proceso === %s', ex.message)

    @api.model
    def send_email(self, subject, body, elapsed_time=False):

        email_from = 'Bulonfer SA <noresponder@bulonfer.com.ar>'
        emails = self.env['ir.config_parameter'].get_param('email_notification', '')

        email_to = emails.split(',')
        #email_to = ['jorge.obiols@gmail.com', 'sagomez@gmail.com']

        if elapsed_time:
            elapsed = str(timedelta(seconds=elapsed_time))
            body += ', duracion: ' + elapsed

        try:
            smtp = self.env['ir.mail_server']
            message = smtp.build_email(email_from, email_to, subject, body)
            smtp.send_email(message)
        except MailDeliveryException as ex:
            raise Exception(ex.message)
