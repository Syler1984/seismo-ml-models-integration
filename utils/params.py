import configparser
from copy import deepcopy


def import_from(path):
    path = path.split('!')[0]
    module, name = path.split(':')
    module = __import__(module, fromlist=[name])
    return getattr(module, name)


class ParamsDictionary(dict):
    """
    Works the same as ordinary dictionary with getting and setting items, except it doesnt raise KeyError
    but returns None if key is missing.
    It also gets nested indexing as tuple, eg config['default', 'loader'] rather than config['default']['loader']
    """

    def __init__(self, data=None):
        super().__init__()
        if type(data) is dict:
            self._dict = deepcopy(data)
        else:
            self._dict = dict()

    def __getitem__(self, key):
        try:
            if type(key) is tuple:
                item = self
                for x in key:
                    item = item[x]
                return item
            else:
                return self._dict[key]
        except KeyError:
            return None
        except TypeError:
            return None

    def __setitem__(self, key, value):
        if type(key) is tuple:
            item = self
            for i in range(len(key) - 1):
                if key[i] not in item:
                    if value is None:
                        return
                    item[key[i]] = ParamsDictionary()
                item = item[key[i]]
            if key[-1] not in item and value is None:
                return
            item[key[-1]] = value
        else:
            self._dict[key] = value

    def __str__(self):
        return self._dict.__str__()

    def __repr__(self):
        return self._dict.__repr__()

    def __len__(self):
        return len(self._dict)

    def __contains__(self, item):
        return item in self._dict

    def items(self):
        return self._dict.items()

    def __iter__(self):
        for key in self._dict:
            yield key


def merge_dictionaries(to_dict, from_dict, depth=3, replace=True):
    """
    Merges both dictionaries, overwriting data in to_dict with from_dict data with the same keys.
    Note: Although function does return merged data, actions are inplace and rewrite to_dict.
    :return: merged dictionaries, returns to_dict reference after the merge.
    """
    for key, value in from_dict.items():

        if issubclass(type(value), dict) and key in to_dict and issubclass(type(to_dict[key]), dict) and depth:
            merge_dictionaries(to_dict[key], value, depth - 1, replace=replace)
        elif not replace and key in to_dict:
            continue
        else:
            to_dict[key] = value

    return to_dict


def configparse_to_dict(parsed, ignore=None, depth=3):
    """
    Turns configparse to dictionary.
    :param parsed:
    :param ignore:
    :param depth:
    :return:
    """
    if ignore is None:
        ignore = ['DEFAULT']

    d_result = ParamsDictionary()
    for key, data in parsed.items():

        if key in ignore:
            continue
        if type(data) is configparser.SectionProxy and depth:
            d_result[key] = configparse_to_dict(data, ignore=ignore, depth=depth - 1)
        elif type(data) is not configparser.SectionProxy:
            d_result[key] = data

    return d_result


class Params:

    def __init__(self, config=None, data=None, other=None, path=None, mode='config', default_dictionary=None):
        """
        :param default_dictionary - string name of a dictionary inside params
                                    or None ("config", "data", "other" or None)
        """
        self.config = ParamsDictionary(config)
        self.data = ParamsDictionary(data)
        self.other = ParamsDictionary(other)
        self.default_dictionary = default_dictionary

        if path:
            self.read_config(path, mode)

        loader, arg = self.default()

        if loader:
            default(loader=loader, arg=arg, params=self)

    def parse_ini(self, path, mode):
        """

        :param path:
        :param mode: 'config', 'data', 'other'
        :return:
        """
        import configparser
        config = configparser.ConfigParser()
        config.read(path)
        data = configparse_to_dict(config)

        if mode == 'config':
            merge_dictionaries(self.config, data)
        elif mode == 'data':
            merge_dictionaries(self.data, data)
        elif mode == 'other':
            merge_dictionaries(self.other, data)

    def read_config(self, path, mode):
        """

        :param path:
        :param mode:
        :return:
        """
        from os.path import splitext
        _, extension = splitext(path)
        if extension == '.ini':
            self.parse_ini(path, mode)
        else:
            AttributeError(f'Unsupported file extension {extension}')

    def merge(self, params, replace=True):
        """
        Merges another params into itself. All fields which share a key will be overwritten by fields from
        params argument.
        """
        merge_dictionaries(self.config, params.config, replace=replace)
        merge_dictionaries(self.data, params.data, replace=replace)
        merge_dictionaries(self.other, params.other, replace=replace)

    def __str__(self):
        r_str = 'Params object:\n' \
                '\t.config:\n' \
                f'{self.config}\n' \
                '\t.data:\n' \
                f'{self.data}\n' \
                '\t.other:\n' \
                f'{self.other}'
        return r_str

    def __repr__(self):
        return self.__str__()

    def __bool__(self):
        params_dict = None
        if self.default_dictionary == 'config':
            params_dict = self.config
        elif self.default_dictionary == 'data':
            params_dict = self.data
        elif self.default_dictionary == 'other':
            params_dict = self.other

        if params_dict:
            return True

        for x in [self.config, self.data, self.other]:
            if x:
                return True
        return False

    def default(self):
        """
        Checks and returns default loader import path and argument if present. Returns (None, None) otherwise.
        :return:
        """
        loader = self.config['default', 'loader']
        arg = self.config['default', 'arg']

        return loader, arg

    def __getitem__(self, key):
        """
        Returns an item from default dictionary: if first key is found in first level of dictionary: returns entry from
            this dictionary if present.
        If first key is not found in first level, searches "main" dictionary.
        If nothing is found in first level dictionary, returns entry from the "main" dictionary, or None.
        """
        params_dict = None
        if self.default_dictionary == 'config':
            params_dict = self.config
        elif self.default_dictionary == 'data':
            params_dict = self.data
        elif self.default_dictionary == 'other':
            params_dict = self.other

        if not params_dict:
            raise KeyError(f'No default dictionary specified for params to access key: {key}')

        # Convert key to iterable if str
        if type(key) is str:
            key = tuple([key])

        if key[0] in params_dict:
            result = params_dict.__getitem__(key)
            if result is None:
                return params_dict.__getitem__(('main', *key[1:]))
            return result
        return params_dict.__getitem__(('main', *key))

    def __setitem__(self, key, value):
        """
        Sets value to a default dictionary key.
        """
        if self.default_dictionary == 'config':
            params_dict = self.config
        elif self.default_dictionary == 'data':
            params_dict = self.data
        elif self.default_dictionary == 'other':
            params_dict = self.other
        else:
            raise KeyError(f'No default dictionary specified for params to set key {key} with value {value}')

        params_dict.__setitem__(key, value)

    def apply_function(self, key, function):
        """
        Applies function to a parameter. If first level dictionary is not specified in key, than applies
        function for all parameter entries in every first level dictionary.
        Applied function should take two positional arguments: parameter value, dictionary (ParamsDictionary to be
        specific) of the same level as the parameter. This function should returns new value for the parameter.
        """
        params_dict = None
        if self.default_dictionary == 'config':
            params_dict = self.config
        elif self.default_dictionary == 'data':
            params_dict = self.data
        elif self.default_dictionary == 'other':
            params_dict = self.other

        # Convert key to iterable if str
        if type(key) is str:
            key = tuple([key])

        if not params_dict:
            raise KeyError(f'No default dictionary specified for params to apply function to key: {key}')

        if key[0] in params_dict:
            result = params_dict.__getitem__(key)
            result = function(result, params_dict.__getitem__(key[0]))
            params_dict.__setitem__(key, result)
        else:
            for x in params_dict:
                result = params_dict.__getitem__((x, *key))
                result = function(result, params_dict.__getitem__(x))
                params_dict.__setitem__((x, *key), result)


def applied_function(**kwargs):
    """
    This is a Python @decorator for converting function to be able to work with Params.apply_function by replacing
    keyword arguments by **kwargs (basically, constants).

    Usage examples:

    @applied_function(v_type = float, name = 'some_name')
    def foo(value, params, v_type, name):
        ...
    params.apply_function('some_key', foo)

    OR

    def foo(value, params, v_type, name):
        ...
    params.apply_function('some_key_1', applied_function(v_type = float, name = 'float_var')(foo))
    params.apply_function('some_key_2', applied_function(v_type = int, name = 'int_var')(foo))

    etc.
    """
    def decorator(f):
        def decorate(value, params):
            return f(value, params, **kwargs)
        return decorate
    return decorator


def default(loader='', params=None, arg=None):
    """
    Returns a default parameters object for a requested module or script.
    :param loader: Name of the module or script.
    :param params:
    :param arg:
    :return:
    """
    default_function = import_from(loader)
    default_params = default_function(arg)

    if not params:
        return default_params
    else:
        params.merge(default_params, replace=False)
        return params
