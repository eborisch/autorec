def execfile(filename, _globals=None, _locals=None):
    with open(filename, 'rb') as srcfile:
        comp = compile(srcfile.read(), filename, 'exec')
    if _globals and _locals:
        return exec(comp, _globals, _locals)
    if _globals:
        return exec(comp, _globals)
    return exec(comp)
