sql = """
CREATE TABLE attachment (
         type            text,
         id              text,
         filename        text,
         size            integer,
         time            integer,
         description     text,
         author          text,
         ipnr            text,
         UNIQUE(type,id,filename)
);
"""

def do_upgrade(env, ver, cursor):
    cursor.execute(sql)
    env.set_config('attachment', 'max_size', '262144')
    env.save_config()
