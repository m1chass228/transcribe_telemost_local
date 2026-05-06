import configparser
import os

class Config:
    def __init__(self, path='config.ini'):
        self.config = configparser.ConfigParser()
        self.config.read(path, encoding='utf-8')

    def get(self, section, option, fallback=None):
        return self.config.get(section, option, fallback=fallback)

    def getint(self, section, option, fallback=None):
        return self.config.getint(section, option, fallback=fallback)

    def getfloat(self, section, option, fallback=None):
        return self.config.getfloat(section, option, fallback=fallback)

# Создаем глобальный объект настроек
cfg = Config()
