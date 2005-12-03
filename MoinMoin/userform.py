# -*- coding: iso-8859-1 -*-
"""
    MoinMoin - UserPreferences Form and User Browser

    @copyright: 2001-2004 by J�rgen Hermann <jh@web.de>
    @license: GNU GPL, see COPYING for details.
"""

import string, time, re, Cookie
from MoinMoin import user, util, wikiutil
from MoinMoin.util import web, mail, datetime
from MoinMoin.widget import html

_debug = 0

#############################################################################
### Form POST Handling
#############################################################################

def savedata(request):
    """ Handle POST request of the user preferences form.

    Return error msg or None.  
    """
    return UserSettingsHandler(request).handleData()


class UserSettingsHandler:

    def __init__(self, request):
        """ Initialize user settings form. """
        self.request = request
        self._ = request.getText
        self.cfg = request.cfg

    def decodePageList(self, key):
        """ Decode list of pages from form input

        Each line is a page name, empty lines ignored.

        Items can use '_' as spaces, needed by [name_with_spaces label]
        format used in quicklinks. We do not touch those names here, the
        underscores are handled later by the theme code.

        @param key: the form key to get
        @rtype: list of unicode strings
        @return: list of normalized names
        """
        text = self.request.form.get(key, [''])[0]
        text = text.replace('\r', '')
        items = []
        for item in text.split('\n'):
            item = item.strip()
            if not item:
                continue
            # Normalize names - except [name_with_spaces label]
            # Commented out to allow URLs
            #if not (item.startswith('[') and item.endswith(']')):
            #    item = self.request.normalizePagename(item)
            items.append(item)
        return items

    def handleData(self):
        _ = self._
        form = self.request.form
    
        if form.has_key('logout'):
            # clear the cookie in the browser and locally. Does not
            # check if we have a valid user logged, just make sure we
            # don't have one after this call.
            self.request.deleteCookie()
            return _("Cookie deleted. You are now logged out.")
    
        if form.has_key('account_sendmail'):
            if not self.cfg.mail_enabled:
                return _("""This wiki is not enabled for mail processing.
Contact the owner of the wiki, who can enable email.""")
            try:
                email = form['email'][0].lower()
            except KeyError:
                return _("Please provide a valid email address!")
    
            users = user.getUserList(self.request)
            for uid in users:
                theuser = user.User(self.request, uid)
                if theuser.valid and theuser.email.lower() == email:
                    msg = theuser.mailAccountData()
                    return wikiutil.escape(msg)

            return _("Found no account matching the given email address '%(email)s'!") % {'email': wikiutil.escape(email)}

        if form.has_key('login'):
            # Trying to login with a user name and a password

            # Require valid user name
            name = form.get('name', [''])[0]
            if not user.isValidName(self.request, name):
                return _("""Invalid user name {{{'%s'}}}.
Name may contain any Unicode alpha numeric character, with optional one
space between words. Group page name is not allowed.""") % wikiutil.escape(name)

            # Check that user exists
            if not user.getUserId(self.request, name):
                return _('Unknown user name: {{{"%s"}}}. Please enter'
                         ' user name and password.') % name

            # Require password
            password = form.get('password',[None])[0]
            if not password:
                return _("Missing password. Please enter user name and password.")

            # Load the user data and check for validness
            theuser = user.User(self.request, name=name, password=password,
                                auth_method='login_userpassword')
            if not theuser.valid:
                if theuser.disabled:
                    return _('Account "%s" is disabled.') % name
                else:
                    return _("Sorry, wrong password.")

            # Save the user and send a cookie
            self.request.user = theuser
            self.request.setCookie()

        elif form.has_key('uid'):
            # Trying to login with the login URL, soon to be removed!
            try:
                 uid = form['uid'][0]
            except KeyError:
                 return _("Bad relogin URL.")

            # Load the user data and check for validness
            theuser = user.User(self.request, uid,
                                auth_method='login_uid')
            if not theuser.valid:
                return _("Unknown user.")
            
            # Save the user and send a cookie
            self.request.user = theuser
            self.request.setCookie()           
        
        
        elif (form.has_key('create') or
              form.has_key('create_only') or
              form.has_key('create_and_mail')):
            if self.request.request_method != 'POST':
                return _("Use UserPreferences to change your settings or create an account.")
            # Create user profile
            if form.has_key('create'):
                theuser = self.request.get_user()
            else:
                theuser = user.User(self.request, auth_method="request:152")
                
            # Require non-empty name
            try:
                theuser.name = form['name'][0]
            except KeyError:
                return _("Empty user name. Please enter a user name.")

            # Don't allow users with invalid names
            if not user.isValidName(self.request, theuser.name):
                return _("""Invalid user name {{{'%s'}}}.
Name may contain any Unicode alpha numeric character, with optional one
space between words. Group page name is not allowed.""") % wikiutil.escape(theuser.name)

            # Is this an existing user trying to change information or a new user?
            # Name required to be unique. Check if name belong to another user.
            newuser = 1
            if user.getUserId(self.request, theuser.name):
                if theuser.name != self.request.user.name:
                    return _("This user name already belongs to somebody else.")
                else:
                    newuser = 0

            # try to get the password and pw repeat
            password = form.get('password', [''])[0]
            password2 = form.get('password2',[''])[0]

            # Check if password is given and matches with password repeat
            if password != password2:
                return _("Passwords don't match!")
            if not password and newuser:
                return _("Please specify a password!")
            # Encode password
            if password and not password.startswith('{SHA}'):
                try:
                    theuser.enc_password = user.encodePassword(password)
                except UnicodeError, err:
                    # Should never happen
                    return "Can't encode password: %s" % str(err)

            # try to get the (required) email
            email = form.get('email', [''])[0]
            theuser.email = email.strip()
            if not theuser.email:
                return _("Please provide your email address. If you lose your"
                         " login information, you can get it by email.")

            # Email should be unique - see also MoinMoin/scripts/moin_usercheck.py
            if theuser.email and self.request.cfg.user_email_unique:
                users = user.getUserList(self.request)
                for uid in users:
                    if uid == theuser.id:
                        continue
                    thisuser = user.User(self.request, uid)
                    if thisuser.email == theuser.email:
                        return _("This email already belongs to somebody else.")

            # save data and send cookie
            theuser.save()
            if form.has_key('create'):
                self.request.user = theuser
                self.request.setCookie()

            if form.has_key('create_and_mail'):
                theuser.mailAccountData()
            
            result = _("User account created!")
            if _debug:
                result = result + util.dumpFormData(form)
            return result

        else: # Save user profile
            if self.request.request_method != 'POST':
                return _("Use UserPreferences to change your settings or create an account.")
            theuser = self.request.get_user()
                
            if not 'name' in theuser.auth_attribs:
                # Require non-empty name
                theuser.name = form.get('name', [theuser.name])[0]
            if not theuser.name:
                return _("Empty user name. Please enter a user name.")

            # Don't allow users with invalid names
            if not user.isValidName(self.request, theuser.name):
                return _("""Invalid user name {{{'%s'}}}.
Name may contain any Unicode alpha numeric character, with optional one
space between words. Group page name is not allowed.""") % wikiutil.escape(theuser.name)

            # Is this an existing user trying to change information or a new user?
            # Name required to be unique. Check if name belong to another user.
            newuser = 1
            if user.getUserId(self.request, theuser.name):
                if theuser.name != self.request.user.name:
                    return _("This user name already belongs to somebody else.")
                else:
                    newuser = 0

            if not 'password' in theuser.auth_attribs:
                # try to get the password and pw repeat
                password = form.get('password', [''])[0]
                password2 = form.get('password2',[''])[0]

                # Check if password is given and matches with password repeat
                if password != password2:
                    return _("Passwords don't match!")
                if not password and newuser:
                    return _("Please specify a password!")
                # Encode password
                if password and not password.startswith('{SHA}'):
                    try:
                        theuser.enc_password = user.encodePassword(password)
                    except UnicodeError, err:
                        # Should never happen
                        return "Can't encode password: %s" % str(err)

            if not 'email' in theuser.auth_attribs:
                # try to get the email
                email = form.get('email', [theuser.email])[0]
                theuser.email = email.strip()

            # Require email
            if not theuser.email:
                return _("Please provide your email address. If you lose your"
                         " login information, you can get it by email.")

            # Email should be unique - see also MoinMoin/scripts/moin_usercheck.py
            if theuser.email and self.request.cfg.user_email_unique:
                users = user.getUserList(self.request)
                for uid in users:
                    if uid == theuser.id:
                        continue
                    thisuser = user.User(self.request, uid, auth_method='userform:283')
                    if thisuser.email == theuser.email:
                        return _("This email already belongs to somebody else.")

            if not 'aliasname' in theuser.auth_attribs:
                # aliasname
                theuser.aliasname = form.get('aliasname', [theuser.aliasname])[0]
	    
            # editor size
            theuser.edit_rows = util.web.getIntegerInput(self.request, 'edit_rows', theuser.edit_rows, 10, 60)
                
            # try to get the editor
            theuser.editor_default = form.get('editor_default', [self.cfg.editor_default])[0]
            theuser.editor_ui = form.get('editor_ui', [self.cfg.editor_ui])[0]

            # time zone
            theuser.tz_offset = util.web.getIntegerInput(self.request, 'tz_offset', theuser.tz_offset, -84600, 84600)
    
            # datetime format
            try:
                dt_d_combined = UserSettings._date_formats.get(form['datetime_fmt'][0], '')
                theuser.datetime_fmt, theuser.date_fmt = dt_d_combined.split(' & ')
            except (KeyError, ValueError):
                pass
    
            # try to get the (optional) theme
            theme_name = form.get('theme_name', [self.cfg.theme_default])[0]
            if theme_name != theuser.theme_name:
                # if the theme has changed, load the new theme
                # so the user has a direct feedback
                # WARNING: this should be refactored (i.e. theme load
                # after userform handling), cause currently the
                # already loaded theme is just replaced (works cause
                # nothing has been emitted yet)
                theuser.theme_name = theme_name
                if self.request.loadTheme(theuser.theme_name) > 0:
                    theme_name = wikiutil.escape(theme_name)
                    return _("The theme '%(theme_name)s' could not be loaded!") % locals()

            # User CSS URL
            key = 'css_url'
            default = self.cfg.user_form_defaults[key]
            if not key in self.cfg.user_form_disable:
                value = form.get(key, [''])[0]
                setattr(theuser, key, value)
            
            # try to get the (optional) preferred language
            theuser.language = form.get('language', [''])[0]

            # checkbox options
            if not newuser:
                for key, label in self.cfg.user_checkbox_fields:
                    if key not in self.cfg.user_checkbox_disable and key not in self.cfg.user_checkbox_remove:
                        value = form.get(key, ["0"])[0]
                        try:
                            value = int(value)
                        except ValueError:
                            pass
                        else:
                            setattr(theuser, key, value)
    
            # quicklinks for navibar
            theuser.quicklinks = self.decodePageList('quicklinks')            
            
            # subscription for page change notification
            theuser.subscribed_pages = self.decodePageList('subscribed_pages')
                    
            # save data
            theuser.save()            
            self.request.user = theuser

            if theuser.auth_method == 'moin_cookie':
                self.request.setCookie()

            result = _("User preferences saved!")
            if _debug:
                result = result + util.dumpFormData(form)
            return result


#############################################################################
### Form Generation
#############################################################################

class UserSettings:
    """ User login and settings management. """

    _date_formats = { # datetime_fmt & date_fmt
        'iso':  '%Y-%m-%d %H:%M:%S & %Y-%m-%d',
        'us':   '%m/%d/%Y %I:%M:%S %p & %m/%d/%Y',
        'euro': '%d.%m.%Y %H:%M:%S & %d.%m.%Y',
        'rfc':  '%a %b %d %H:%M:%S %Y & %a %b %d %Y',
    }

    def __init__(self, request):
        """ Initialize user settings form.
        """
        self.request = request
        self._ = request.getText
        self.cfg = request.cfg

    def _tz_select(self):
        """ Create time zone selection. """
        tz = 0
        if self.request.user.valid:
            tz = int(self.request.user.tz_offset)

        options = []
        now = time.time()
        for halfhour in range(-47, 48):
            offset = halfhour * 1800
            t = now + offset

            options.append((
                str(offset),
                '%s [%s%s:%s]' % (
                    time.strftime(self.cfg.datetime_fmt, util.datetime.tmtuple(t)),
                    "+-"[offset < 0],
                    string.zfill("%d" % (abs(offset) / 3600), 2),
                    string.zfill("%d" % (abs(offset) % 3600 / 60), 2),
                ),
            ))
 
        return util.web.makeSelection('tz_offset', options, str(tz))


    def _dtfmt_select(self):
        """ Create date format selection. """
        _ = self._
        try:
            dt_d_combined = '%s & %s' % (self.request.user.datetime_fmt, self.request.user.date_fmt)
            selected = [
                k for k, v in self._date_formats.items()
                    if v == dt_d_combined][0]
        except IndexError:
            selected = ''
        options = [('', _('Default'))] + self._date_formats.items()

        return util.web.makeSelection('datetime_fmt', options, selected)


    def _lang_select(self):
        """ Create language selection. """
        from MoinMoin import i18n
        from MoinMoin.i18n import NAME
        _ = self._
        cur_lang = self.request.user.valid and self.request.user.language or ''
        langs = i18n.wikiLanguages().items()
        langs.sort(lambda x,y,NAME=NAME: cmp(x[1][NAME], y[1][NAME]))
        options = [('', _('<Browser setting>', formatted=False))]
        for lang in langs:
            name = lang[1][NAME]
            options.append((lang[0], name))
                
        return util.web.makeSelection('language', options, cur_lang)
  
    def _theme_select(self):
        """ Create theme selection. """
        cur_theme = self.request.user.valid and self.request.user.theme_name or self.cfg.theme_default
        options = [("<default>", "<%s>" % self._("Default"))]
        for theme in wikiutil.getPlugins('theme', self.request.cfg):
            options.append((theme, theme))
                
        return util.web.makeSelection('theme_name', options, cur_theme)
  
    def _editor_default_select(self):
        """ Create editor selection. """
        editor_default = self.request.user.valid and self.request.user.editor_default or self.cfg.editor_default
        options = [("<default>", "<%s>" % self._("Default"))]
        for editor in ['text','gui',]:
            options.append((editor, editor))
        return util.web.makeSelection('editor_default', options, editor_default)

    def _editor_ui_select(self):
        """ Create editor selection. """
        editor_ui = self.request.user.valid and self.request.user.editor_ui or self.cfg.editor_ui
        options = [("<default>", "<%s>" % self._("Default")),
                   ("theonepreferred", self._("the one preferred")),
                   ("freechoice", self._("free choice")),
                  ]
        return util.web.makeSelection('editor_ui', options, editor_ui)
                
    def make_form(self):
        """ Create the FORM, and the TABLE with the input fields
        """
        sn = self.request.getScriptname()
        pi = self.request.getPathinfo()
        action = u"%s%s" % (sn, pi)
        self._form = html.FORM(action=action)
        self._table = html.TABLE(border="0")

        # Use the user interface language and direction
        lang_attr = self.request.theme.ui_lang_attr()
        self._form.append(html.Raw('<div class="userpref"%s>' % lang_attr))

        self._form.append(html.INPUT(type="hidden", name="action", value="userform"))
        self._form.append(self._table)
        self._form.append(html.Raw("</div>"))


    def make_row(self, label, cell, **kw):
        """ Create a row in the form table.
        """
        self._table.append(html.TR().extend([
            html.TD(**kw).extend([html.B().append(label), '   ']),
            html.TD().extend(cell),
        ]))


    def asHTML(self, create_only=False):
        """ Create the complete HTML form code. """
        _ = self._
        self.make_form()

        if self.request.user.valid and not create_only:
            buttons = [('save', _('Save'))]
            if self.request.user.auth_method == 'moin_cookie':
                buttons.append(('logout', _('Logout')))
            uf_remove = self.cfg.user_form_remove
            uf_disable = self.cfg.user_form_disable
            for attr in self.request.user.auth_attribs:
                if attr == 'password':
                    uf_remove.append(attr)
                    uf_remove.append('password2')
                else:
                    uf_disable.append(attr)
            for key, label, type, length, textafter in self.cfg.user_form_fields:
                default = self.cfg.user_form_defaults[key]
                if not key in uf_remove:
                    if key in uf_disable:
                        self.make_row(_(label),
                                  [ html.INPUT(type=type, size=length, name=key, disabled="disabled",
                                    value=getattr(self.request.user, key)), ' ', _(textafter), ])
                    else:
                        self.make_row(_(label),
                                  [ html.INPUT(type=type, size=length, name=key, value=getattr(self.request.user, key)), ' ', _(textafter), ])

            if not self.cfg.theme_force and not "theme_name" in self.cfg.user_form_remove:
                self.make_row(_('Preferred theme'), [self._theme_select()])

            if not self.cfg.editor_force:
                if not "editor_default" in self.cfg.user_form_remove:
                    self.make_row(_('Editor Preference'), [self._editor_default_select()])
                if not "editor_ui" in self.cfg.user_form_remove:
                    self.make_row(_('Editor shown on UI'), [self._editor_ui_select()])

            if not "tz_offset" in self.cfg.user_form_remove:
                self.make_row(_('Time zone'), [
                    _('Your time is'), ' ',
                    self._tz_select(),
                    html.BR(),
                    _('Server time is'), ' ',
                    time.strftime(self.cfg.datetime_fmt, util.datetime.tmtuple()),
                    ' (UTC)',
                ])

            if not "datetime_fmt" in self.cfg.user_form_remove:
                self.make_row(_('Date format'), [self._dtfmt_select()])

            if not "language" in self.cfg.user_form_remove:
                self.make_row(_('Preferred language'), [self._lang_select()])
            
            # boolean user options
            bool_options = []
            checkbox_fields = self.cfg.user_checkbox_fields
            _ = self.request.getText
            checkbox_fields.sort(lambda a, b: cmp(a[1](_), b[1](_)))
            for key, label in checkbox_fields:
                if not key in self.cfg.user_checkbox_remove:
                    bool_options.extend([
                        html.INPUT(type="checkbox", name=key, value="1",
                            checked=getattr(self.request.user, key, 0),
                            disabled=key in self.cfg.user_checkbox_disable and True or None),
                        ' ', label(_), html.BR(),
                    ])
            self.make_row(_('General options'), bool_options, valign="top")

            self.make_row(_('Quick links'), [
                html.TEXTAREA(name="quicklinks", rows="6", cols="50")
                    .append('\n'.join(self.request.user.getQuickLinks())),
            ], valign="top")

            # subscribed pages
            if self.cfg.mail_enabled:
                # Get list of subscribe pages, DO NOT sort! it should
                # stay in the order the user entered it in his input
                # box.
                notifylist = self.request.user.getSubscriptionList()

                warning = []
                if not self.request.user.email:
                    warning = [
                        html.BR(),
                        html.SMALL(Class="warning").append(
                            _("This list does not work, unless you have"
                              " entered a valid email address!")
                        )]
                
                self.make_row(
                    html.Raw(_('Subscribed wiki pages (one regex per line)')),
                    [html.TEXTAREA(name="subscribed_pages", rows="6", cols="50").append(
                        '\n'.join(notifylist)),
                    ] + warning,
                    valign="top"
                )
        else: # not logged in
            # Login / register interface
            buttons = [
                # IMPORTANT: login should be first to be the default
                # button when a user hits ENTER.
                ('login', _('Login')),
                ("create", _('Create Profile')),
            ]
            for key, label, type, length, textafter in self.cfg.user_form_fields:
                if key in ('name', 'password', 'password2', 'email'):
                    self.make_row(_(label),
                              [ html.INPUT(type=type, size=length, name=key,
                                           value=''),
                                ' ', _(textafter), ])

        if self.cfg.mail_enabled:
            buttons.append(("account_sendmail", _('Mail me my account data')))

        if create_only:
            buttons = [("create_only", _('Create Profile'))]
            if self.cfg.mail_enabled:
                buttons.append(("create_and_mail", "%s + %s" %
                                (_('Create Profile'), _('Email'))))

        # Add buttons
        button_cell = []
        for name, label in buttons:
            if not name in self.cfg.user_form_remove:
                button_cell.extend([
                    html.INPUT(type="submit", name=name, value=label),
                    ' ',
                ])
        self.make_row('', button_cell)

        return unicode(self._form)


def getUserForm(request, create_only=False):
    """ Return HTML code for the user settings. """
    return UserSettings(request).asHTML(create_only=create_only)


#############################################################################
### User account administration
#############################################################################

def do_user_browser(request):
    """ Browser for SystemAdmin macro. """
    from MoinMoin.util.dataset import TupleDataset, Column
    from MoinMoin.Page import Page
    _ = request.getText

    data = TupleDataset()
    data.columns = [
        #Column('id', label=('ID'), align='right'),
        Column('name', label=('Username')),
        Column('email', label=('Email')),
        Column('action', label=_('Action')),
    ]

    # Iterate over users
    for uid in user.getUserList(request):
        account = user.User(request, uid)

        userhomepage = Page(request, account.name)
        if userhomepage.exists():
            namelink = userhomepage.link_to(request)
        else:
            namelink = account.name

        data.addRow((
            #request.formatter.code(1) + uid + request.formatter.code(0),
            request.formatter.rawHTML(namelink),
            (request.formatter.url(1, 'mailto:' + account.email, css='mailto', unescaped=1) +
             request.formatter.text(account.email) +
             request.formatter.url(0)),
            request.page.link_to(request, text=_('Mail me my account data'),
                                 querystr= {"action":"userform",
                                            "email": account.email,  
                                            "account_sendmail": "1",
                                            "sysadm": "users",})
        ))

    if data:
        from MoinMoin.widget.browser import DataBrowserWidget

        browser = DataBrowserWidget(request)
        browser.setData(data)
        return browser.toHTML()

    # No data
    return ''

