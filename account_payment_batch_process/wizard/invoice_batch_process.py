# Copyright 2019 Open Source Integrators
# <https://www.opensourceintegrators.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from openerp import api, fields, models, _
from openerp.exceptions import UserError, ValidationError


INV_TO_PARTN = {
    'out_invoice': 'customer',
    'out_refund': 'customer',
    'in_invoice': 'supplier',
    'in_refund': 'supplier',
}
# Since invoice amounts are unsigned, this is how we know if money comes in or
# goes out
INV_TO_PAYM_SIGN = {
    'out_invoice': 1,
    'in_refund': 1,
    'in_invoice': -1,
    'out_refund': -1,
}


class InvoiceCustomerPaymentLine(models.TransientModel):
    """
    batch payment record of customer invoices
    """
    _name = "invoice.customer.payment.line"
    _rec_name = 'invoice_id'

    invoice_id = fields.Many2one('account.invoice', string="Customer Invoice",
                                 required=True)
    partner_id = fields.Many2one('res.partner', string="Customer Name",
                                 required=True)
    balance_amt = fields.Float("Invoice Balance", required=True)
    wizard_id = fields.Many2one('account.register.payments', string="Wizard")
    receiving_amt = fields.Float("Receive Amount", required=True)
    check_amount_in_words = fields.Char(string="Amount in Words")
    payment_method_id = fields.Many2one('account.payment.method',
                                        string='Payment Type')
    payment_difference = fields.Float(string='Difference Amount')
    handling = fields.Selection([('open', 'Keep open'),
                                 ('reconcile', 'Mark invoice as fully paid')],
                                default='open',
                                string="Action",
                                copy=False)
    writeoff_account_id = fields.Many2one('account.account', string="Account",
                                          domain=[('deprecated', '=', False)],
                                          copy=False)

    @api.onchange('receiving_amt')
    def _onchange_amount(self):
        self.check_amount_in_words = \
            self.invoice_id.currency_id.amount_to_text(self.receiving_amt)
        self.payment_difference = (self.balance_amt - self.receiving_amt)


class InvoicePaymentLine(models.TransientModel):
    """
    Batch payment record of supplier invoices
    """
    _name = "invoice.payment.line"
    _rec_name = 'invoice_id'

    invoice_id = fields.Many2one('account.invoice', string="Supplier Invoice",
                                 required=True)
    partner_id = fields.Many2one('res.partner', string="Supplier Name",
                                 required=True)
    balance_amt = fields.Float("Balance Amount", required=True)
    wizard_id = fields.Many2one('account.register.payments', string="Wizard")
    paying_amt = fields.Float("Pay Amount", required=True)
    check_amount_in_words = fields.Char(string="Amount in Words")

    @api.onchange('paying_amt')
    def _onchange_amount(self):
        self.check_amount_in_words = \
            self.invoice_id.currency_id.amount_to_text(self.paying_amt)


class AccountRegisterPayments(models.TransientModel):
    """
    Inheritance to make payments in batches
    """
    _inherit = "account.register.payments"

    @api.depends('invoice_customer_payments.receiving_amt')
    def _compute_customer_pay_total(self):
        for rec in self:
            rec.total_customer_pay_amount = sum(
                line.receiving_amt for line in rec.invoice_customer_payments)

    @api.depends('invoice_payments.paying_amt')
    def _compute_pay_total(self):
        for rec in self:
            rec.total_pay_amount = sum(line.paying_amt for line in
                                       rec.invoice_payments)

    is_auto_fill = fields.Char(string="Auto-Fill Pay Amount")
    invoice_payments = fields.One2many('invoice.payment.line', 'wizard_id',
                                       string='Payments')
    is_customer = fields.Boolean(string="Is Customer?")
    invoice_customer_payments = fields.One2many(
        'invoice.customer.payment.line',
        'wizard_id', string='Receipts')
    cheque_amount = fields.Float("Amount to pay",
                                 required=True, default=0.00)
    total_pay_amount = fields.Float("Total Invoices",
                                    compute='_compute_pay_total')
    total_customer_pay_amount = fields.Float(
        "Total Invoices", compute='_compute_customer_pay_total')

    @api.model
    def default_get(self, pfields):
        """
        Get list of bills to pay
        """
        context = dict(self._context or {})
        active_model = context.get('active_model')
        active_ids = context.get('active_ids')
        # Checks on context parameters
        if not active_model or not active_ids:
            raise UserError(
                _("Program error: wizard action executed without"
                  " active_model or active_ids in context."))
        if active_model != 'account.invoice':
            raise UserError(
                _("Program error: the expected model for this"
                  " action is 'account.invoice'. The provided one"
                  " is '%d'.") % active_model)

        # Checks on received invoice records
        invoices = self.env[active_model].browse(active_ids)
        if any(invoice.state != 'open' for invoice in invoices):
            raise UserError(
                _("You can only register payments for open invoices"))
        if any(INV_TO_PARTN[inv.type] != INV_TO_PARTN[invoices[0].type]
               for inv in invoices):
            raise UserError(
                _("You cannot mix customer invoices and vendor"
                  " bills in a single payment."))
        if any(inv.currency_id != invoices[0].currency_id for inv in invoices):
            raise UserError(
                _("In order to pay multiple invoices at once, they"
                  " must use the same currency."))

        rec = {}
        if 'batch' in context and context.get('batch'):
            lines = []
            if INV_TO_PARTN[invoices[0].type] == 'customer':
                for inv in invoices:
                    dict_line = {
                        'partner_id': inv.partner_id.id,
                        'invoice_id': inv.id,
                        'balance_amt': inv.residual or 0.0,
                        'receiving_amt': 0.0,
                        'payment_difference': inv.residual or 0.0,
                        'handling': 'open'
                    }
                    lines.append((0, 0, dict_line))
                dict_val = {
                    'invoice_customer_payments': lines,
                    'is_customer': True
                }
                rec.update(dict_val)
            else:
                for inv in invoices:
                    dict_line = {
                        'partner_id': inv.partner_id.id,
                        'invoice_id': inv.id,
                        'balance_amt': inv.residual or 0.0,
                        'paying_amt': 0.0
                    }
                    lines.append((0, 0, dict_line))
                dict_val = {
                    'invoice_payments': lines,
                    'is_customer': False
                }
                rec.update(dict_val)

        else:
            # Checks on received invoice records
            if any(INV_TO_PARTN[inv.type] != INV_TO_PARTN[invoices[0].type]
                   for inv in invoices):
                raise UserError(
                    _("You cannot mix customer invoices and"
                      " vendor bills in a single payment."))

        if 'batch' in context and context.get('batch'):
            total_amount = sum(
                inv.residual * INV_TO_PAYM_SIGN[inv.type] for inv in invoices)

            dict_val_rec = {
                'amount': abs(total_amount),
                'currency_id': invoices[0].currency_id.id,
                'payment_type': total_amount > 0 and 'inbound' or 'outbound',
                'partner_id': invoices[0].commercial_partner_id.id,
                'partner_type': INV_TO_PARTN[invoices[0].type],
            }
            rec.update(dict_val_rec)
        else:
            rec = super(AccountRegisterPayments, self).default_get(pfields)

        return rec

    def get_payment_batch_vals(self, group_data=None):
        """
        Get values to save in the batch payment
        """
        if not group_data:
            return {}
        """
        val_payment_m = \
            group_data['payment_method_id'] \
            if 'payment_method_id' in group_data \
            else self.payment_method_id.id
        res = {
            'journal_id': self.journal_id.id,
            'payment_method_id': val_payment_m,
            'payment_date': self.payment_date,
            'communication': group_data['memo'],
            'invoice_ids': [(4, int(inv), None)
                            for inv in list(group_data['inv_val'])],
            'payment_type': self.payment_type,
            'amount': group_data['total'],
            'currency_id': self.currency_id.id,
            'partner_id': int(group_data['partner_id']),
            'partner_type': group_data['partner_type'],
        }
        p_model = self.env.ref(
            'account_check_printing.account_payment_method_check')
        if self.payment_method_id == p_model:
            p_data_total = group_data['total_check_amount_in_words']
            dict_val_rec = {
                'check_amount_in_words': p_data_total or '',
            }
            res.update(dict_val_rec)
        """
        def get_payment_data():
            ret = {
                'payment_type_copy': 'outbound',
                'journal_id': self.journal_id.id,
                'amount': group_data['total'],
                'currency_id': self.currency_id.id,
                'payment_date': self.payment_date,
                'communication': group_data['memo'],
                'payment_method_id': self.payment_method_id.id,
                'payment_type': 'outbound',
                'partner_type': group_data['partner_type'],
            }
            return ret

        res = {
            'payment_date': self.payment_date,
            'communication': group_data['memo'],
            'currency_id': self.currency_id.id,
            'partner_id': int(group_data['partner_id']),
            'partner_type': group_data['partner_type'],
            'payment_ids': [(0, False, get_payment_data())]
        }
        return res

    @api.multi
    def make_payments_customer(self):
        """
        Dictionary for the payment to each customer invoice
        """
        data = {}
        for paym in self.invoice_customer_payments:
            if paym.receiving_amt > 0:
                paym.payment_difference = \
                    (paym.balance_amt - paym.receiving_amt)
                partner_id = str(paym.invoice_id.partner_id.id)
                if partner_id in data:
                    old_total = data[partner_id]['total']
                    # Build memo value
                    if self.communication:
                        memo = ''.join([data[partner_id]['memo'], ' : ',
                                        self.communication, '-',
                                        str(paym.invoice_id.number)])
                    else:
                        p_memo = [data[partner_id]['memo'], ' : ',
                                  str(paym.invoice_id.number)]
                        memo = ''.join(p_memo)
                    # Calculate amount in words
                    amount_total = (old_total + paym.receiving_amt)
                    amount_word = \
                        self.currency_id.amount_to_text(amount_total)
                    p_method_pay = \
                        paym.payment_method_id.id \
                        if paym.payment_method_id else False
                    dict_data_part = {
                        'partner_id': partner_id,
                        'partner_type': INV_TO_PARTN[paym.invoice_id.type],
                        'total': amount_total,
                        'memo': memo,
                        'payment_method_id': p_method_pay,
                        'total_check_amount_in_words': amount_word
                    }
                    data[partner_id].update(dict_data_part)
                    dict_data_part_inv = {
                        str(paym.invoice_id.id): {
                            'receiving_amt': paym.receiving_amt,
                            'handling': paym.handling,
                            'payment_difference': paym.payment_difference,
                            'writeoff_account_id': paym.writeoff_account_id and
                            paym.writeoff_account_id.id or False
                        }
                    }
                    data[partner_id]['inv_val'].update(dict_data_part_inv)
                else:
                    # Build memo value
                    if self.communication:
                        memo = ''.join([self.communication, '-',
                                        str(paym.invoice_id.number)])
                    else:
                        memo = str(paym.invoice_id.number)
                    # Calculate amount in words
                    dict_payment_method_id = \
                        paym.payment_method_id.id \
                        if paym.payment_method_id else False
                    amount_word = self.currency_id.amount_to_text(
                        paym.receiving_amt)
                    dict_writeoff_account_id = \
                        paym.writeoff_account_id.id \
                        if paym.writeoff_account_id else False
                    dict_data_upd = {
                        partner_id: {
                            'partner_id': partner_id,
                            'partner_type': INV_TO_PARTN[
                                paym.invoice_id.type],
                            'total': paym.receiving_amt,
                            'payment_method_id': dict_payment_method_id,
                            'total_check_amount_in_words': amount_word,
                            'memo': memo,
                            'inv_val': {
                                str(paym.invoice_id.id): {
                                    'receiving_amt': paym.receiving_amt,
                                    'handling': paym.handling,
                                    'payment_difference':
                                    paym.payment_difference,
                                    'writeoff_account_id':
                                    dict_writeoff_account_id
                                }
                            }
                        }
                    }
                    data.update(dict_data_upd)
        return data

    @api.multi
    def make_payments_supplier(self):
        """
        Dictionary for the payment to each supplier invoice
        """
        data = {}
        for paym in self.invoice_payments:
            if paym.paying_amt > 0:
                partner_id = str(paym.invoice_id.partner_id.id)
                if partner_id in data:
                    old_total = data[partner_id]['total']
                    # Build memo value
                    if self.communication:
                        p_memo = [
                            data[partner_id]['memo'], ' : ',
                            self.communication, '-',
                            str(paym.invoice_id.number)
                        ]
                        memo = ''.join(p_memo)
                    else:
                        p_memo = [
                            data[partner_id]['memo'], ' : ',
                            str(paym.invoice_id.number)
                        ]
                        memo = ''.join(p_memo)
                    # Calculate amount in words
                    amount_total = old_total + paym.paying_amt
                    amount_word = \
                        self.currency_id.amount_to_text(amount_total)
                    dict_val_part_inv = {
                        'partner_id': partner_id,
                        'partner_type': INV_TO_PARTN[
                            paym.invoice_id.type],
                        'total': amount_total,
                        'memo': memo,
                        'total_check_amount_in_words': amount_word
                    }
                    data[partner_id].update(dict_val_part_inv)
                    dict_val_up = {
                        str(paym.invoice_id.id): paym.paying_amt
                    }
                    data[partner_id]['inv_val'].update(dict_val_up)
                else:
                    # Build memo value
                    if self.communication:
                        p_memo = [
                            self.communication, '-',
                            str(paym.invoice_id.number)
                        ]
                        memo = ''.join(p_memo)
                    else:
                        memo = str(paym.invoice_id.number)
                    # Calculate amount in words
                    amount_word = \
                        self.currency_id.amount_to_text(paym.paying_amt)
                    dict_val_up = {
                        partner_id: {
                            'partner_id': partner_id,
                            'partner_type': INV_TO_PARTN[
                                paym.invoice_id.type],
                            'total': paym.paying_amt,
                            'total_check_amount_in_words': amount_word,
                            'memo': memo,
                            'inv_val': {
                                str(paym.invoice_id.id): paym.paying_amt
                            }
                        }
                    }
                    data.update(dict_val_up)
        return data

    @api.multi
    def make_payments(self):
        """
        Action make payments
        """

        # Make group data either for Customers or Vendors
        context = dict(self._context or {})
        data = {}
        if self.is_customer:
            context.update({'is_customer': True})
            if self.total_customer_pay_amount != self.cheque_amount:
                raise ValidationError(
                    _('Verification Failed! Total Invoices'
                      ' Amount and Check amount does not'
                      ' match!.'))

            for paym in self.invoice_customer_payments:
                if not paym.payment_method_id:
                    raise ValidationError(
                        _('Verification Failed! Payment Method'
                          ' must be indicate.'))

            data = self.make_payments_customer()

        else:
            context.update({'is_customer': False})
            if self.total_pay_amount != self.cheque_amount:
                raise ValidationError(
                    _('Verification Failed! Total Invoices'
                      ' Amount and Check amount does not'
                      ' match!.'))

            for paym in self.invoice_payments:
                if (paym.balance_amt - paym.paying_amt) < 0.00:
                    raise ValidationError(
                        _('Verification Failed! Amount'
                          ' not must be bigest.'))

            data = self.make_payments_supplier()

        # Update context
        dict_val = {
            'group_data': data
        }
        context.update(dict_val)
        # Making partner wise payment

        import wdb;wdb.set_trace()

        payment_ids = []
        for p_index in list(data):
            val_ap = self.env['account.payment.group']
            payment = val_ap.with_context(context).\
                create(self.get_payment_batch_vals(group_data=data[p_index]))
            payment_ids.append(payment.id)
            payment.post()

        view_id = self.env['ir.model.data'].get_object_reference(
            'account_payment_batch_process',
            'view_account_supplier_payment_tree_nocreate')[1]
        return {
            'name': _('Payments'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'account.payment',
            'view_id': view_id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'domain': "[('id','in',%s)]" % (payment_ids),
            'context': {'group_by': 'partner_id'}
        }

    @api.multi
    def auto_fill_payments(self):
        """
        Action auto fill payments
        """
        ctx = self._context.copy()
        for wiz in self:
            if wiz.is_customer:
                if wiz.invoice_customer_payments:
                    for payline in wiz.invoice_customer_payments:
                        payline.write({'receiving_amt': payline.balance_amt,
                                       'payment_difference': 0.0})
                ctx.update({'reference': wiz.communication or '',
                            'journal_id': wiz.journal_id.id})
            else:
                if wiz.invoice_payments:
                    for payline in wiz.invoice_payments:
                        payline.write({'paying_amt': payline.balance_amt})
                ctx.update({'reference': wiz.communication or '',
                            'journal_id': wiz.journal_id.id})

        return {
            'name': _("Batch Payments"),
            'view_mode': 'form',
            'view_id': False,
            'view_type': 'form',
            'res_id': self.id,
            'res_model': 'account.register.payments',
            'type': 'ir.actions.act_window',
            'nodestroy': True,
            'target': 'new',
            'context': ctx
        }
