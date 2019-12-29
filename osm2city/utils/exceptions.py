class MyException(Exception):
    """A custom exception in osm2city, when you do not want to preserve the original one.

    E.g use as follows:
    ...
    except IOError as e:
        raise MyException('Something spectacular happened') from e
    """
    pass
