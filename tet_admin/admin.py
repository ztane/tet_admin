from pyramid.view import view_config
from sqlalchemy import orm, inspect
from liilak.model import DBSession
from paginate import Page
import paginate
import operator


class SaAdminGenerator(object):
    def __init__(self, *a, **kw):
        if not a:
            a = orm._mapper_registry.keys()

        self.includes = set()
        self.excludes = set()

        self.include(*a)
        if 'exclude' in kw:
            self.exclude(*list(kw.pop('exclude')))

        if kw:
            raise TypeError("__init__ got an unexpected keyword argument %s"
                % kw.keys()[0])

    def include(self, *a):
        classes = self._extract_classes(a)
        self.includes |= set(classes)

    def exclude(self, *a):
        classes = self._extract_classes(a)
        self.excludes |= set(classes)

    def _extract_classes(self, thelist):
        retval = []
        for i in thelist:
            # it is a mapped class
            if hasattr(i, '__mapper__'):
                retval.append(i)
                continue

            # it is a declarative base
            if hasattr(i, '_decl_class_registry'):
                classes = i._decl_class_registry.values()
                retval.extend(self._extract_classes(classes))
                continue

            # it is a mapper
            if getattr(i, 'class_', None):
                retval.extend(self._extract_classes([i.class_]))

        return retval

    def get_classes(self):
        classes = self.includes - self.excludes
        return list(classes)

    def prepare_admin_data(self):
        classes = self.get_classes()
        self.admin_data = SaAdminData(classes)


class ModelClassData(object):
    def __init__(self, class_):
        self.class_      = class_
        self.name        = class_.__name__
        self.pretty_name = class_.__name__
        self.url_name    = class_.__name__


class SaAdminData(object):
    def __init__(self, model_classes):
        self.model_class_data = [ ModelClassData(i) for i in model_classes ]
        self.model_class_data.sort(key=operator.attrgetter('pretty_name'))

        self.url_to_model_class = { i.url_name: i for i in self.model_class_data }


class ModelNode(object):
    def __init__(self, request, model_data):
        self.model_data = model_data


class RootNode(object):
    def __init__(self, request, admin_data):
        self.request = request
        self.admin_data = admin_data

    def __getitem__(self, name):
        data = self.admin_data.url_to_model_class[name]
        return ModelNode(self.request, data)


@view_config(name='', route_name='sa-pyramid-admin.main', context=RootNode, renderer='tet_admin:templates/admin-root.pt')
def root_view(context, request):
    return dict(model_classes=context.admin_data.model_class_data)


@view_config(name='', route_name='sa-pyramid-admin.main', context=ModelNode, renderer='tet_admin:templates/model-root.pt')
def model_view(context, request):
    page_number = request.GET.get('page', '1')

    try:
        page_number = int(page_number)
    except:
        page_number = 1

    model = context.model_data.class_
    page = SqlalchemyOrmPage(DBSession.query(model), page=page_number)

    pager = page.pager(url=request.path_url + "?page=$page")
    return dict(model_data=context.model_data, pager=pager, items=page.items)


class SaPyramidAdminGenerator(SaAdminGenerator):
    def plant(self, config, route_prefix=''):
        self.prepare_admin_data()


        config.add_static_view(name='%s/__static__', path='tet_admin:static')
        config.add_route('sa-pyramid-admin.main',
            '%s/*traverse' % route_prefix, factory=self.root_factory)
        config.scan()


    def root_factory(self, request):
        return RootNode(request, self.admin_data)


class SqlalchemyOrmWrapper(object):
    """Wrapper class to access elements of a collection."""
    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, range):
        # Return a range of objects of an sqlalchemy.orm.query.Query object
        return self.obj[range]

    def __len__(self):
        # Count the number of objects in an sqlalchemy.orm.query.Query object
        return self.obj.count()


try:
    unicode
except:
    unicode = str

import uuid
import datetime

encoders = {
    int: int,
    bytes: lambda b: binascii.hexlify(b).decode('ascii'),
    unicode: unicode,
    uuid.UUID: str,
    datetime: str
}

decoders = {
    int: int,
    bytes: lambda v: binascii.unhexlify(v.encode('ascii')),
    unicode: unicode,
    uuid.UUID: uuid.UUID
}

class DefaultKeyDeriver(object):
    def __init__(self, class_):
        self.class_ = class_
        mapper = inspect(class_)
        primary_key_columns = mapper.primary_key
        pk_types = [ i.type.python_type for i in primary_key_columns ]
        for i in pk_types:
            if i not in encoders:
                raise ValueError("Unable to generate urls for primary key column type %s")

    def encode_key(self, instance):
        rv = []

    def decode_key(self, key):
        pass


class SqlalchemyOrmPage(paginate.Page):
    """A pagination page that deals with SQLAlchemy ORM objects."""
    def __init__(self, *args, **kwargs):
        super(SqlalchemyOrmPage, self).__init__(*args, wrapper_class=SqlalchemyOrmWrapper, **kwargs)

