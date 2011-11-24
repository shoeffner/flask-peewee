import datetime

from flask import request, session, url_for

from flaskext.admin import ModelAdmin, AdminPanel
from flaskext.tests.base import FlaskPeeweeTestCase
from flaskext.tests.test_app import User, Message, Note, admin
from flaskext.utils import get_next, make_password, check_password

from wtfpeewee.orm import model_form


class AdminTestCase(FlaskPeeweeTestCase):
    def login(self, context=None):
        context = context or self.app
        context.post('/accounts/login/', data={
            'username': 'admin',
            'password': 'admin',
        })
    
    def logout(self, context=None):
        context = context or self.app
        context.post('/accounts/logout/')
    
    def test_admin_auth(self):
        self.create_users()
        
        # check login redirect
        resp = self.app.get('/admin/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['location'], 'http://localhost/accounts/login/?next=%2Fadmin%2F')
        
        # try logging in as a normal user, get a 403 forbidden
        resp = self.app.post('/accounts/login/?next=%2Fadmin%2F', data={
            'username': 'normal',
            'password': 'normal',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['location'], 'http://localhost/admin/')
        
        resp = self.app.get('/admin/')
        self.assertEqual(resp.status_code, 403)
        
        # log out from normal user
        resp = self.app.get('/accounts/logout/')
        
        # try logging in as an admin and get a 200
        resp = self.app.post('/accounts/login/?next=%2Fadmin%2F', data={
            'username': 'admin',
            'password': 'admin',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['location'], 'http://localhost/admin/')
        
        resp = self.app.get('/admin/')
        self.assertEqual(resp.status_code, 200)
    
    def test_url_resolution(self):
        # need to be in a 'request' context to use ``url_for``
        with self.flask_app.test_request_context('/'):
            # admin urls
            self.assertEqual(url_for('admin.index'), '/admin/')
            
            # modeladmin urls
            self.assertEqual(url_for('admin.user_index'), '/admin/user/')
            self.assertEqual(url_for('admin.user_add'), '/admin/user/add/')
            self.assertEqual(url_for('admin.user_edit', pk=1), '/admin/user/1/')
            self.assertEqual(url_for('admin.user_delete'), '/admin/user/delete/')
            
            # panel urls
            self.assertEqual(url_for('admin.panel_notes_create'), '/admin/notes/create/')
    
    def test_index_view(self):
        self.create_users()
        self.login()
        
        # check for context in the index view
        resp = self.app.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        
        # check that we have the stuff from the auth module and the index view
        self.assertContext('user', self.admin)
        self.assertContext('model_admins', [
            admin._registry['message'],
            admin._registry['note'],
            admin._registry['user'],
        ])
        self.assertContext('panels', [
            admin._panels['Notes'],
        ])
    
    def test_model_admin_add(self):
        self.create_users()
        self.assertEqual(User.select().count(), 3)
        
        with self.flask_app.test_client() as c:
            self.login(c)
            
            # the add url returns a 200
            resp = c.get('/admin/user/add/')
            self.assertEqual(resp.status_code, 200)
            
            # ensure the user, model_admin and form are correct in the context
            self.assertContext('user', self.admin)
            self.assertContext('model_admin', admin._registry['user'])
            
            self.assertTrue('form' in self.flask_app._template_context)
            frm = self.flask_app._template_context['form']
            self.assertEqual(sorted(frm._fields.keys()), [
                'active',
                'admin',
                'email',
                'join_date',
                'password',
                'username',
            ])
            
            # make an incomplete post and get a 200 with errors
            resp = c.post('/admin/user/add/', data={
                'username': '',
                'password': 'xxx',
                'active': '1',
                'email': '',
                'join_date': '2011-01-01 00:00:00',
            })
            self.assertEqual(resp.status_code, 200)
            
            # no new user created
            self.assertEqual(User.select().count(), 3)
            
            # check the form for errors
            frm = self.get_context('form')
            self.assertEqual(frm.errors, {
                'username': ['This field is required.'],
                'email': ['This field is required.'],
            })
            
            # make a complete post and get a 302 to the edit page
            resp = c.post('/admin/user/add/', data={
                'username': 'new',
                'password': 'new',
                'active': '1',
                'email': 'new@new.new',
                'join_date': '2011-01-01 00:00:00',
            })
            self.assertEqual(resp.status_code, 302)
            
            # new user was created
            self.assertEqual(User.select().count(), 4)
            
            # check they have the correct data on the new instance
            user = User.get(username='new')
            self.assertEqual(user.active, True)
            self.assertEqual(user.admin, False)
            self.assertEqual(user.email, 'new@new.new')
            self.assertEqual(user.join_date, datetime.datetime(2011, 1, 1))
            self.assertTrue(check_password('new', user.password))
            
            # check the redirect was correct
            self.assertTrue(resp.headers['location'].endswith('/admin/user/%d/' % user.id))
    
    def test_model_admin_edit(self):
        users = self.create_users()
        self.assertEqual(User.select().count(), 3)
        
        # grab an id so we can test a 404 on non-existent user
        unused_id = [x for x in range(1, 5) if not User.filter(id=x).exists()][0]
        
        with self.flask_app.test_client() as c:
            self.login(c)
            
            # nonexistant user 404s
            resp = c.get('/admin/user/%d/' % unused_id)
            self.assertEqual(resp.status_code, 404)
            
            # edit page returns a 200
            resp = c.get('/admin/user/%d/' % self.normal.id)
            self.assertEqual(resp.status_code, 200)
            
            # check the user, model_admin and form are correct in the context
            self.assertContext('user', self.admin)
            self.assertContext('model_admin', admin._registry['user'])
            
            self.assertTrue('form' in self.flask_app._template_context)
            frm = self.flask_app._template_context['form']
            self.assertEqual(sorted(frm._fields.keys()), [
                'active',
                'admin',
                'email',
                'join_date',
                'password',
                'username',
            ])
            
            # check the form pulled the right data off the model
            self.assertEqual(frm.data, {
                'username': 'normal',
                'password': frm.password.data, # skip this
                'email': '',
                'admin': False,
                'active': True,
                'join_date': frm.join_date.data, # microseconds...bleh
            })
            
            # make an incomplete post to update the user and get a 200 w/errors
            resp = c.post('/admin/user/%d/' % self.normal.id, data={
                'username': '',
                'password': '',
                'active': '1',
                'email': 'fap@fap.fap',
                'join_date': '2011-01-01 00:00:00',
            })
            self.assertEqual(resp.status_code, 200)
            
            # no new user created
            self.assertEqual(User.select().count(), 3)
            
            # refresh database content
            normal = User.get(id=self.normal.id)
            self.assertEqual(normal.username, 'normal') # was not saved
            
            # check the form for errors
            frm = self.get_context('form')
            self.assertEqual(frm.errors, {
                'username': ['This field is required.'],
                'password': ['This field is required.'],
            })
            
            # make a complete post
            resp = c.post('/admin/user/%d/' % self.normal.id, data={
                'username': 'edited',
                'password': 'edited',
                'active': '1',
                'email': 'x@x.x',
                'join_date': '2011-01-01 00:00:00',
            })
            self.assertEqual(resp.status_code, 302)
            
            # no new user was created
            self.assertEqual(User.select().count(), 3)
            
            # grab from the database
            user = User.get(username='edited')
            self.assertEqual(user.id, self.normal.id) # it is the same user
            
            self.assertTrue(check_password('edited', user.password))
            self.assertEqual(user.active, True)
            self.assertEqual(user.admin, False)
            self.assertEqual(user.email, 'x@x.x')
            self.assertEqual(user.join_date, datetime.datetime(2011, 1, 1))
            
            self.assertTrue(resp.headers['location'].endswith('/admin/user/%d/' % user.id))
            
            # make another post without modifying the password, should stay same
            resp = c.post('/admin/user/%d/' % user.id, data={
                'username': 'edited2',
                'password': user.password,
                'active': '1',
                'email': 'x@x.x',
                'join_date': '2011-01-01 00:00:00',
            })
            self.assertEqual(resp.status_code, 302)
            
            # no new user was created
            self.assertEqual(User.select().count(), 3)
            
            # grab from the database
            user = User.get(username='edited2')
            self.assertEqual(user.id, self.normal.id) # it is the same user
            
            # the password has not changed
            self.assertTrue(check_password('edited', user.password))
    
    def test_model_admin_delete(self):
        self.create_users()
        
        with self.flask_app.test_client() as c:
            self.login(c)
            
            # do a basic get, nothing much going on
            resp = c.get('/admin/user/delete/')
            self.assertEqual(resp.status_code, 200)
            
            self.assertContext('user', self.admin)
            self.assertContext('model_admin', admin._registry['user'])
            
            query = self.get_context('query')
            self.assertEqual(list(query), [])
            
            # send it a single id
            resp = c.get('/admin/user/delete/?id=%d' % (self.normal.id))
            self.assertEqual(resp.status_code, 200)
            
            query = self.get_context('query')
            self.assertEqual(list(query), [self.normal])
            
            # ensure nothing was deleted
            self.assertEqual(User.select().count(), 3)
            
            # post to it, get a redirect on success
            resp = c.post('/admin/user/delete/', data={'id': self.normal.id})
            self.assertEqual(resp.status_code, 302)
            
            # ensure the user was deleted
            self.assertEqual(User.select().count(), 2)
            self.assertRaises(User.DoesNotExist, User.get, id=self.normal.id)
            
            self.assertTrue(resp.headers['location'].endswith('/admin/user/'))
            
            # do a multi-delete
            resp = c.get('/admin/user/delete/?id=%d&id=%d' % (self.admin.id, self.inactive.id))
            self.assertEqual(resp.status_code, 200)
            
            query = self.get_context('query')
            self.assertEqual(list(query), [self.admin, self.inactive])
            
            # post to it and check both deleted
            resp = c.post('/admin/user/delete/', data={'id': [self.admin.id, self.inactive.id]})
            self.assertEqual(resp.status_code, 302)
            
            self.assertEqual(User.select().count(), 0)
    
    def test_model_admin_index(self):
        self.create_users()
        
        with self.flask_app.test_client() as c:
            self.login(c)
            
            resp = c.get('/admin/user/?ordering=username')
            self.assertEqual(resp.status_code, 200)
            
            self.assertContext('user', self.admin)
            self.assertContext('model_admin', admin._registry['user'])
            self.assertContext('ordering', 'username')
            
            query_filter = self.get_context('query_filter')
            self.assertEqual(query_filter.raw_lookups, [])
                        
            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), [
                self.admin,
                self.inactive,
                self.normal,
            ])
            
            self.assertEqual(query.get_page(), 1)
            self.assertEqual(query.get_pages(), 1)
    
    def test_model_admin_index_filters(self):
        users = self.create_users()
        notes = {}
        
        for user in users:
            notes[user] = [Note.create(user=user, message='test-%d' % i) for i in range(3)]
        
        norm2 = self.create_user('normal2', 'normal2')
        
        with self.flask_app.test_client() as c:
            self.login(c)
            
            # test a simple lookup
            resp = c.get('/admin/user/?username__eq=admin')
            self.assertEqual(resp.status_code, 200)
            
            self.assertContext('user', self.admin)
            self.assertContext('model_admin', admin._registry['user'])
            self.assertContext('ordering', '')

            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), [
                self.admin,
            ])
            
            # test a lookup using multiple values joined with "eq"
            resp = c.get('/admin/user/?username__eq=admin&username__eq=normal&ordering=-username')
            self.assertEqual(resp.status_code, 200)

            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), [
                self.normal,
                self.admin,
            ])
            
            # test a lookup using "in"
            resp = c.get('/admin/user/?username__in=admin&username__in=normal&ordering=-username')
            self.assertEqual(resp.status_code, 200)

            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), [
                self.normal,
                self.admin,
            ])
            
            # test a lookup using partial string
            resp = c.get('/admin/user/?username__startswith=norm&ordering=-username')
            self.assertEqual(resp.status_code, 200)

            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), [
                norm2,
                self.normal,
            ])
            
            # test a lookup spanning a relation
            resp = c.get('/admin/note/?user_id__eq=%d' % self.normal.id)
            self.assertEqual(resp.status_code, 200)
            
            self.assertContext('model_admin', admin._registry['note'])
            
            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), notes[self.normal])
            
            # test a multi-value lookup spanning a relation
            resp = c.get('/admin/note/?user_id__in=%d&user_id__in=%d' % (self.normal.id, self.admin.id))
            self.assertEqual(resp.status_code, 200)
            
            self.assertContext('model_admin', admin._registry['note'])
            
            query = self.get_context('query')
            expected_notes = notes[self.admin] + notes[self.normal]
            self.assertEqual(list(query.get_list()), expected_notes)
        
    def test_model_admin_index_pagination(self):
        users = self.create_users()
        notes = {}
        
        for user in users:
            notes[user] = [Note.create(user=user, message='test-%d' % i) for i in range(20)]
        
        with self.flask_app.test_client() as c:
            self.login(c)
            
            # test a simple lookup
            resp = c.get('/admin/note/?ordering=id')
            self.assertEqual(resp.status_code, 200)
            
            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), notes[users[0]])
            
            resp = c.get('/admin/note/?ordering=id&page=2')
            self.assertEqual(resp.status_code, 200)
            
            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), notes[users[1]])
            
            resp = c.get('/admin/note/?ordering=id&page=1&user=%d&user=%d' % (users[1].id, users[2].id))
            self.assertEqual(resp.status_code, 200)
            
            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), notes[users[1]])
            
            resp = c.get('/admin/note/?ordering=id&page=2&user=%d&user=%d' % (users[1].id, users[2].id))
            self.assertEqual(resp.status_code, 200)
            
            query = self.get_context('query')
            self.assertEqual(list(query.get_list()), notes[users[2]])
    
    def test_panel_simple(self):
        users = self.create_users()
        
        with self.flask_app.test_client() as c:
            self.login(c)
            
            self.assertEqual(Note.select().count(), 0)
            
            resp = c.post('/admin/notes/create/', data={'message': 'testing'})
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp.headers['location'].endswith('/admin/'))
            
            self.assertEqual(Note.select().count(), 1)
            
            note = Note.get(user=self.admin)
            self.assertEqual(note.message, 'testing')


class TemplateHelperTestCase(FlaskPeeweeTestCase):
    def setUp(self):
        super(TemplateHelperTestCase, self).setUp()
        self.create_users()
        self.create_message(self.admin, 'admin message')
        self.create_message(self.admin, 'admin message 2')
        self.create_message(self.normal, 'normal message')
        
        self.th = admin.template_helper
    
    def test_get_model_field(self):
        self.assertEqual(self.th.get_model_field(self.admin, 'username'), 'admin')
        self.assertEqual(self.th.get_model_field(self.admin, 'message_count'), 2)
        self.assertRaises(AttributeError, self.th.get_model_field, self.admin, 'missing_attr')
    
    def test_get_form_field(self):
        form = model_form(User)(obj=self.admin)
        self.assertEqual(self.th.get_form_field(form, 'username'), form.username)
        self.assertEqual(self.th.get_form_field(form, 'username').data, 'admin')
    
    def test_fix_underscores(self):
        self.assertEqual(self.th.fix_underscores('some_model'), 'Some Model')
        self.assertEqual(self.th.fix_underscores('test'), 'Test')
    
    def test_update_querystring(self):
        self.assertEqual(self.th.update_querystring('', 'page', 1), 'page=1')
        self.assertEqual(self.th.update_querystring('page=1', 'page', 2), 'page=2')
        self.assertEqual(self.th.update_querystring('session=3&page=1', 'page', 2), 'session=3&page=2')
        self.assertEqual(self.th.update_querystring('page=1&session=3', 'page', 2), 'session=3&page=2')
        self.assertEqual(self.th.update_querystring('session=3&page=1&ordering=id', 'page', 2), 'session=3&ordering=id&page=2')
        self.assertEqual(self.th.update_querystring('session=3&ordering=id', 'page', 2), 'session=3&ordering=id&page=2')
    
    def test_get_verbose_name(self):
        self.assertEqual(self.th.get_verbose_name(User, 'username'), 'Username')
        self.assertEqual(self.th.get_verbose_name(User, 'join_date'), 'Join Date')
        self.assertEqual(self.th.get_verbose_name(User, 'admin'), 'Can access admin')
        self.assertEqual(self.th.get_verbose_name(User, 'some_field'), 'Some Field')
    
    def test_get_model_admins(self):
        self.assertEqual(self.th.get_model_admins(), {'model_admins': [
            admin._registry['message'],
            admin._registry['note'],
            admin._registry['user'],
        ]})
