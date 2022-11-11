import os, sys
import pprint
import numpy as np


class AttrDict:

    _freezed = False
    """ Avoid accidental creation of new hierarchies. """

    def __getattr__(self, name):
        if self._freezed:
            raise AttributeError(name)
        if name.startswith("_"):
            # Do not mess with internals. Otherwise copy/pickle will fail
            raise AttributeError(name)
        ret = AttrDict()
        setattr(self, name, ret)
        return ret

    def __setattr__(self, name, value):
        if self._freezed and name not in self.__dict__:
            raise AttributeError("Config was freezed! Unknown config: {}".format(name))
        super().__setattr__(name, value)

    def __str__(self):
        return pprint.pformat(self.to_dict(), indent=1, width=100, compact=True)

    __repr__ = __str__

    def to_dict(self):
        """Convert to a nested dict."""
        return {
            k: v.to_dict() if isinstance(v, AttrDict) else v
            for k, v in self.__dict__.items()
            if not k.startswith("_")
        }

    def from_dict(self, d):
        self.freeze(False)
        for k, v in d.items():
            self_v = getattr(self, k)
            if isinstance(self_v, AttrDict):
                self_v.from_dict(v)
            else:
                setattr(self, k, v)

    def update_args(self, args):
        """Update from command line args."""
        for cfg in args:
            keys, v = cfg.split("=", maxsplit=1)
            keylist = keys.split(".")

            dic = self
            for i, k in enumerate(keylist[:-1]):
                assert k in dir(dic), "Unknown config key: {}".format(keys)
                dic = getattr(dic, k)
            key = keylist[-1]

            oldv = getattr(dic, key)
            if not isinstance(oldv, str):
                v = eval(v)
            setattr(dic, key, v)

    def freeze(self, freezed=True):
        self._freezed = freezed
        for v in self.__dict__.values():
            if isinstance(v, AttrDict):
                v.freeze(freezed)

    # avoid silent bugs
    def __eq__(self, _):
        raise NotImplementedError()

    def __ne__(self, _):
        raise NotImplementedError()


config = AttrDict()
_C = config  # short alias to avoid coding

# Versioning
_C.MAJOR = 1
_C.MINOR = 2
_C.PATCH = 2
_C.VERSION = f"{_C.MAJOR}.{_C.MINOR}.{_C.PATCH}"


class PipelineFolderStructure:
    def __init__(self, out_dir: str):
        self.RAWFILE_DIR = f"{out_dir}/0.rawfiles"
        self.PREPROCESSING_DIR = f"{out_dir}/1.preprocessing"
        self.SEGMENTATION_DIR = f"{out_dir}/2.segmentation"
        self.MEASURING_DIR = f"{out_dir}/3.measuring"
        self.ERROR_LOG_DIR = f"{out_dir}/errors"
