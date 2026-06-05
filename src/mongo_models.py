
from datetime import datetime
from bunnet import Document, Indexed, init_bunnet, TimeSeriesConfig

from pydantic import Field
from typing import Optional

from pymongo import MongoClient

def init_client(MONGO_URL):
    # Wrap the app in middleware.
    client =  MongoClient(MONGO_URL)
    init_bunnet(database=client.gldb, document_models=[User, Folder, Program, Setting])
    return client

class User(Document):
    """A single user of the IDE"""
    # No parent
    # key is the user's unique name
    key: Indexed(str)
    joinDate: datetime = Field(default_factory=datetime.now)
    email: Indexed(str)
    secret: str

    @classmethod
    def query(cond):
        return User.find(cond)


class Folder (Document):
    """A collection of programs created by a user"""
    # Parent is a User
    # key is the folder's name (unique for a user)
    parentID: Indexed(str)
    key: Indexed(str)
    isPublic: bool


class Program (Document):
    """A single program"""
    # Parent is a Folder
    # key is the program's name (unique for a folder)
    parentID: Indexed(str)
    key: Indexed(str)
    description: Optional[str] = None
    source: Optional[str] = None
    screenshot: Optional[bytes] = None
    date_time: datetime = Field(default_factory=datetime.now)

    @property
    def datetime(self):
        return self.date_time

    @datetime.setter
    def datetime(self, value):
        self.date_time = value


class Setting(Document):
    """Key-value settings store"""
    key: Indexed(str, unique=True)
    value: str = 'NOT SET'

