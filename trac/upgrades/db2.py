sql = """
-- Add a keyword column to 'ticket'
CREATE TEMP TABLE ticket_tmp AS
 SELECT * FROM ticket;

DROP TABLE ticket;

CREATE TABLE ticket (
        id              integer PRIMARY KEY,
        time            integer,        -- the time it was created
        changetime      integer,
        component       text,
        severity        text,
        priority        text,
        owner           text,           -- who is this ticket assigned to
        reporter        text,
        cc              text,           -- email addresses to notify
        url             text,           -- url related to this ticket
        version         text,           -- 
        milestone       text,           -- 
        status          text,
        resolution      text,
        summary         text,           -- one-line summary
        description     text,           -- problem description (long)
        keywords        text            -- list of keywords
);

INSERT INTO ticket SELECT *,'' FROM ticket_tmp;
"""

# FIXME: this is a safetyplug until database changes are ready.
sql="" 

def do_upgrade(db, ver):
    cursor = db.cursor()
    cursor.execute(sql)
    db.commit()
    
