from trac.db import Table, Column, Index

def do_upgrade(env, ver, cursor):
    # Add a few new indices to speed things up
    cursor.execute("CREATE INDEX wiki_time_idx ON wiki (time)")
    cursor.execute("CREATE INDEX revision_time_idx ON revision (time)")
    cursor.execute("CREATE INDEX ticket_status_idx ON ticket (status)")
    cursor.execute("CREATE INDEX ticket_time_idx ON ticket (time)")

    # Fix missing single column primary key constraints
    if env.config.get('trac', 'database').startswith('postgres'):
        cursor.execute("ALTER TABLE system ADD CONSTRAINT system_pkey PRIMARY KEY (name)")
        cursor.execute("ALTER TABLE revision ADD CONSTRAINT revision_pkey PRIMARY KEY (rev)")
        cursor.execute("ALTER TABLE ticket ADD CONSTRAINT ticket_pkey PRIMARY KEY (id)")
        cursor.execute("ALTER TABLE component ADD CONSTRAINT component_pkey PRIMARY KEY (name)")
        cursor.execute("ALTER TABLE milestone ADD CONSTRAINT milestone_pkey PRIMARY KEY (name)")
        cursor.execute("ALTER TABLE version ADD CONSTRAINT version_pkey PRIMARY KEY (name)")
        cursor.execute("ALTER TABLE report ADD CONSTRAINT report_pkey PRIMARY KEY (id)")
