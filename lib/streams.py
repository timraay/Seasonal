import sqlite3
db = sqlite3.connect('seasonal.db')
cur = db.cursor()

cur.execute('''CREATE TABLE IF NOT EXISTS "streams" (
	"id"	INTEGER,
	"channel_id"	INTEGER,
	"lang"	TEXT,
	"name"	TEXT,
	"url"	TEXT,
	PRIMARY KEY("id"),
	FOREIGN KEY("channel_id") REFERENCES channels("channel_id")
)''')
db.commit()

FLAGS = dict(
    UK=("EN", "🇬🇧"),
    US=("EN", "🇺🇸"),
    DE=("DE", "🇩🇪"),
    NL=("NL", "🇳🇱"),
    FR=("FR", "🇫🇷"),
    CN=("CN", "🇨🇳"),
    RU=("RU", "🇷🇺"),
    ES=("ES", "🇪🇸"),
    JP=("JP", "🇯🇵"),
    AU=("EN", "🇦🇺"),
)

class Stream:
    def __init__(self, id_: int):
        cur.execute('SELECT * FROM streams WHERE id = ?', (id_,))
        res = cur.fetchone()
        if not res: raise ValueError("There is no stream with ID %s" % id_)

        (self.id, self.channel_id, self.lang, self.name, self.url) = res

    @classmethod
    def new(cls, channel_id: int, lang: str, name: str, url: str):
        cur.execute('SELECT MAX(id) FROM streams')
        (id_,) = cur.fetchone()
        if id_ is None:
            id_ = 0
        else:
            id_ += 1

        cur.execute(
            "INSERT INTO streams VALUES (?,?,?,?,?)",
            (id_, int(channel_id), str(lang).upper(), str(name), str(url))
        )
        db.commit()
        return cls(id_)

    def save(self):
        cur.execute(
            'UPDATE streams SET channel_id = ?, lang = ?, name = ?, url = ? WHERE id = ?',
            (int(self.channel_id), str(self.lang).upper(), str(self.name), str(self.url), int(self.id))
        )
        db.commit()

    def delete(self):
        cur.execute('DELETE FROM streams WHERE id = ?', (self.id,))
        db.commit()
        self = None

    @classmethod
    def in_channel(cls, channel_id: int):
        cur.execute('SELECT id FROM streams WHERE channel_id = ? ORDER BY id', (int(channel_id),))
        return [cls(i) for (i,) in cur.fetchall()]

    @property
    def flag(self):
        lang = self.lang.upper()
        if len(lang) != 2:
            return '❓'
        flags = FLAGS.get(lang, ['??', '❓'])
        return flags[1]
    
    @property
    def displaylang(self):
        lang = self.lang.upper()
        if len(lang) != 2:
            return '??'
        flags = FLAGS.get(lang, ['??', '❓'])
        return flags[0]
        
    def to_text(self, small=False):
        if small:
            return f"[{self.flag}{self.name}]({self.url})"
        else:
            return f"({self.displaylang}) {self.flag} {self.name} - <{self.url}>"
