def execute(hdf, args):
    # Currently hdf is set only when the macro is called
    # From a wiki page
    if hdf:
        hdf.setValue('wiki.macro.greeting', 'Hello World')
        
    # args will be null if the macro is called without parentesis.
    args = args or 'No arguments'
    return 'Hello World, args = ' + args
