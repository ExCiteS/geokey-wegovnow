"""Methods for converting data between systems or formats."""

import sys

if sys.version_info.major < 3:
    # This is supposed to be bad practice, but is the only thing found to work.
    reload(sys)
    sys.setdefaultencoding('utf8')


def make_cm_url(url):
    """Turns a Geokey url into a Community Maps url."""
    protocol, address = url.split('//')
    address_parts = address.split('/')
    new_address_parts = []
    for i, part in enumerate(address_parts):
        if part == 'api':
            continue
        if i == 0 and '-gk-' in part:
            new_address_parts.append(part.replace('-gk-', '-cm-'))
        elif part.endswith('s'):
            new_address_parts.append(part[:-1])
        else:
            new_address_parts.append(part)
    return protocol + '//' + '/'.join(new_address_parts)


def get_link_title(properties):
    """Gets a link title from a properties dictionary."""
    if not properties:
        return "Unknown title"

    # Try plausible fields for link titles.
    possible_title_field_names = ['name', 'title', 'heading', 'main']
    for title in possible_title_field_names:
        for k in properties.keys():
            if str.upper(title) in str.upper(str(k)):
                return properties[k]

    # Fall back to the first items in the dict.
    return ' '.join([str(a) for a in properties.items()[0]])
