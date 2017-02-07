"""Main initialization for the WeGovNow extension."""

VERSION = (2, 0, 0)
__version__ = '.'.join(map(str, VERSION))


try:
    from geokey.extensions.base import register

    register(
        'geokey_wegovnow',
        'WeGovNow',
        display_admin=False,
        superuser=False,
        version=__version__
    )
except BaseException:
    print 'Please install GeoKey first'
