

class baseconfig():
    DEBUG = False

    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.sqlite3'


class localdev(baseconfig):
    DEBUG = True

    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.sqlite3'
    SECRET_KEY = 'shhh_its secret'
    SECURITY_TRACKABLE = True
    SECURITY_TOKEN_AUTHENTICATION_HEADER = 'Authorization'
    UPLOAD_FOLDER = 'static/uploads'

    MAIL_SERVER = 'localhost'
    MAIL_PORT = 1025
    MAIL_DEFAULT_SENDER = 'no-reply@serveease.com'

    CACHE_TYPE = 'RedisCache'
    CACHE_REDIS_URL = 'redis://localhost:6379/3'
    CACHE_DEFAULT_TIMEOUT = 30


class prod(baseconfig):
    DEBUG = False

    SQLALCHEMY_DATABASE_URI = 'sqlite:///test.sqlite3'
    # SECRET_KEY = get.env
    SECURITY_TRACKABLE = True
    SECURITY_TOKEN_AUTHENTICATION_HEADER = 'Authorization'
    UPLOAD_FOLDER = 'static/uploads'

