# -*- coding: utf-8 -*-
import os, sys, redis
print("Python =", sys.executable)
print("VIRTUAL_ENV =", os.getenv("VIRTUAL_ENV"))
print("redis version =", redis.__version__, "module file =", redis.__file__)
r = redis.Redis.from_url(os.getenv("REDIS_URI","redis://localhost:6379/0"))
print("PING =", r.ping())
