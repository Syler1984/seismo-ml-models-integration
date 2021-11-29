import os


def parse_seisan_def(path, params):
    """
    Reads SEISAN.DEF and parses main environment parameters (does not parse stations).
    """
    pattern = 'ARC_ARCHIVE'
    l_pattern = len(pattern)
    with open(path, 'r') as file:
        lines = file.readlines()
        for line in lines:
            if line[:l_pattern] == pattern:
                archive_path = line.split()
                if len(archive_path) == 2:
                    params['main', 'archives'] = archive_path[1].strip()
                break


def parse_unix(params):
    """
    Parses environment variables in UNIX systems and passes them to params, if not set earlier
    (through config file or command line arguments).
    """
    seisan_top = os.environ.get('SEISAN_TOP')
    default_database = os.environ.get('DEF_BASE')
    if not seisan_top:
        return

    seisan_path = os.path.join(seisan_top, 'DAT/SEISAN.DEF')
    mulplt_path = os.path.join(seisan_top, 'DAT/MULPLT.DEF')

    parse_seisan_def(seisan_path, params)

    print('seisan: ', params['main', 'seisan'])
    print('seisan exists: ', params.key_exists(('main', 'seisan')))
    if not params.key_exists(('main', 'seisan')):
        print('seisan!')
        params['main', 'seisan'] = seisan_path
    if not params.key_exists(('main', 'mulplt')):
        print('mulplt!')
        params['main', 'mulplt'] = mulplt_path


def archive_scan(params):
    parse_unix(params)