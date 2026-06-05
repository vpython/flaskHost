from . import mongo_models
from . import ndb_models
import os
import abc

MONGO_URL = os.environ.get('MONGO_URL', None)

class DBGlue(abc.ABC):
    """     
    This class is used to translate the database calls from the
    application to the database. This allows for a single point
    of translation between the application and the database.
    """

    @abc.abstractmethod
    def wrap_app(self, app):
        pass

    @abc.abstractmethod
    def get_id(self, obj):
        pass

    @abc.abstractmethod
    def get_user(self, email):
        pass

    @abc.abstractmethod
    def get_user_byusername(self, username):
        pass

    @abc.abstractmethod
    def new_user(self, user_id, email, secret):
        pass

    @abc.abstractmethod
    def folders(self, user_id):
        pass

    @abc.abstractmethod
    def folder(self, user, folder):
        pass

    @abc.abstractmethod
    def new_folder(self, user_obj, folder_name, public):
        pass

    @abc.abstractmethod
    def delete_folder(self, folder_obj):
        pass

    @abc.abstractmethod
    def programs(self, user, folder):
        pass

    @abc.abstractmethod
    def program(self, user, folder, program):
        pass

    @abc.abstractmethod
    def new_program(self, folder_obj, program_name):
        pass

    @abc.abstractmethod
    def put_program(self, program_obj):
        pass

    @abc.abstractmethod
    def delete_program(self, program_obj):
        pass

    @abc.abstractmethod
    def set_datetime(self, obj, dt):
        pass

    @abc.abstractmethod
    def count_users(self):
        """Return the current number of User records."""
        pass

    @abc.abstractmethod
    def get_setting(self, key):
        """Return the value string for the given setting key, or None if not set."""
        pass

    @abc.abstractmethod
    def set_setting(self, key, value):
        """Persist value string for the given setting key (upsert)."""
        pass


class NDB_DBGlue(DBGlue):

    def wrap_app(self, app):
        # Wrap the app in middleware.
        ndb_models.wrap_app(app)
        return app

    def get_id(self, obj):
        return obj.key.id()

    def get_user(self, email):
        return ndb_models.User.query(ndb_models.User.email == email).get()

    def get_user_byusername(self, username):
        return ndb_models.ndb.Key("User", username).get()

    def new_user(self, user_id, email, secret):
        """
        Create a new user, and two default folders.
        """
        db_user = ndb_models.User(id=user_id, email=email, secret=secret)
        db_user.put()
        db_my_programs = ndb_models.Folder(
            parent=db_user.key, id="MyPrograms", isPublic=True)
        db_my_programs.put()

        db_my_programs = ndb_models.Folder(
            parent=db_user.key, id="Private", isPublic=False)
        db_my_programs.put()
        return db_user

    def folders(self, user_id):
        return ndb_models.Folder.query(ancestor=ndb_models.ndb.Key("User", user_id))

    def folder(self, user, folder):
        return ndb_models.Folder.query(ancestor=ndb_models.ndb.Key("User", user, "Folder", folder)).get()

    def new_folder(self, user_obj, folder_name, public):
        new_fold=ndb_models.Folder(parent=user_obj.key, id=folder_name, isPublic=public)
        new_fold.put()
        return new_fold

    def delete_folder(self, folder_obj):
        folder_obj.key.delete()

    def programs(self, user, folder):
        return ndb_models.Program.query(ancestor=ndb_models.ndb.Key("User", user, "Folder", folder))

    def program(self, user, folder, program):
        return ndb_models.ndb.Key("User", user, "Folder", folder, "Program", program).get()

    def new_program(self, folder_obj, program_name):
        new_prog=ndb_models.Program(parent=folder_obj.key, id=program_name)
        new_prog.put()
        return new_prog

    def put_program(self, program_obj):
        program_obj.put()

    def delete_program(self, program_obj):
        program_obj.key.delete()

    def set_datetime(self, obj, dt):
        obj.datetime = dt

    def count_users(self):
        return ndb_models.User.query().count()

    def get_setting(self, key):
        setting = ndb_models.ndb.Key('Setting', key).get()
        if not setting or setting.value == 'NOT SET':
            return None
        return setting.value

    def set_setting(self, key, value):
        setting = ndb_models.ndb.Key('Setting', key).get()
        if not setting:
            setting = ndb_models.Setting(id=key)
        setting.value = value
        setting.put()


class MONGO_DBGlue(DBGlue):

    def wrap_app(self, app):
        # init the Mongo client
        self.client =  mongo_models.init_client(MONGO_URL)
        return app

    def get_id(self, obj):
        return obj.key

    def get_user(self, email):
        return mongo_models.User.find({"email":email}).first_or_none()

    def get_user_byusername(self, username):
        return mongo_models.User.find({"key":username}).first_or_none()

    def new_user(self, user_id, email, secret):
        """
        Create a new user, and two default folders.
        """
        db_user = mongo_models.User(key=user_id, email=email, secret=secret)
        db_user.insert()

        db_my_programs = mongo_models.Folder(parentID=str(db_user.id), key="MyPrograms", isPublic=True)
        db_my_programs.insert()

        db_my_programs = mongo_models.Folder(parentID=str(db_user.id), key="Private", isPublic=False)
        db_my_programs.insert()

        return db_user

    def folders(self, user_id):
        db_user = self.get_user_byusername(user_id)
        if not db_user:
            raise Exception("User not found")
        return mongo_models.Folder.find({"parentID":str(db_user.id)}).to_list()

    def folder(self, user_id, folder):
        db_user = self.get_user_byusername(user_id)
        if not db_user:
            raise Exception("User not found")
        return mongo_models.Folder.find({"parentID":str(db_user.id), "key":folder}).first_or_none()

    def new_folder(self, user_obj, folder_name, public):
        new_fold=mongo_models.Folder(parentID=str(user_obj.id), key=folder_name, isPublic=public)
        new_fold.insert()
        return new_fold

    def delete_folder(self, folder_obj):
        folder_obj.delete()

    def programs(self, user_id, folder):
        db_folder = self.folder(user_id, folder)
        if not db_folder:
            raise Exception("Folder not found")
        return mongo_models.Program.find({"parentID":str(db_folder.id)}).to_list()

    def program(self, user_id, folder, program):
        db_folder = self.folder(user_id, folder)
        if not db_folder:
            raise Exception("Folder not found")
        return mongo_models.Program.find({"parentID":str(db_folder.id), "key":program}).first_or_none()

    def new_program(self, folder_obj, program_name):
        new_prog=mongo_models.Program(parentID=str(folder_obj.id), key=program_name)
        new_prog.insert()
        return new_prog

    def put_program(self, program_obj):
        program_obj.save()

    def delete_program(self, program_obj):
        program_obj.delete()

    def set_datetime(self, obj, dt):
        obj.date_time = dt

    def count_users(self):
        return self.client.gldb['User'].count_documents({})

    def get_setting(self, key):
        setting = mongo_models.Setting.find({"key": key}).first_or_none()
        if not setting or setting.value == 'NOT SET':
            return None
        return setting.value

    def set_setting(self, key, value):
        setting = mongo_models.Setting.find({"key": key}).first_or_none()
        if setting is None:
            setting = mongo_models.Setting(key=key, value=value)
        else:
            setting.value = value
        setting.save()


def setupDB():
    """ If MONGO_URL is set, use MongoDB, otherwise use NDB """
    if MONGO_URL:
        return MONGO_DBGlue()
    else:
        return NDB_DBGlue()


db = setupDB()
