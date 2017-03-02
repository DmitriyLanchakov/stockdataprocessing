import psycopg2
from StockDataDownloader import StockDataDownloader
from Conf import DbConfig, Config
from datetime import datetime, timedelta
import oandapyV20
from dateutil import parser
import re

step = 60*300  # secs
dbConf = DbConfig.DbConfig()
conf = Config.Config()
connect = psycopg2.connect(database=dbConf.dbname, user=dbConf.user, host=dbConf.address, password=dbConf.password)
cursor = connect.cursor()

print 'Successfully connected'
cursor.execute("SELECT * FROM pg_tables WHERE schemaname='public';")
tables = list()
for row in cursor:
    tables.append(row[1])
for name in tables:
    cmd = "DROP TABLE " + name
    print cmd
    cursor.execute(cmd)
connect.commit()

tName = conf.insName.lower()
cmd = ('CREATE TABLE public."{0}" (' \
       'datetimestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,' \
       'ask FLOAT NOT NULL,' \
       'bid FLOAT NOT NULL,' \
       'volume FLOAT NOT NULL,' \
       'CONSTRAINT "PK_ID" PRIMARY KEY ("datetimestamp"));' \
       'CREATE UNIQUE INDEX timestamp_idx ON {0} ("datetimestamp");').format(tName)
cursor.execute(cmd)
connect.commit()

print 'Created table', tName

daysTotal = 10
timeStep = 5 # s

downloader = StockDataDownloader.StockDataDownloader()
oanda = oandapyV20.API(environment=conf.env, access_token=conf.token)


def parse_date(dt):
    broken = re.search(
        r'([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.([0-9]+))?(Z|([+-][0-9]{2}):([0-9]{2}))',
        dt)
    return (datetime(
        year=int(broken.group(1)),
        month=int(broken.group(2)),
        day=int(broken.group(3)),
        hour=int(broken.group(4)),
        minute=int(broken.group(5)),
        second=int(broken.group(6)),
        microsecond=int(broken.group(8) or "0")))


date = datetime.utcnow() - timedelta(days=daysTotal)
dateStop = datetime.utcnow()

last_id = datetime.min
while date < dateStop - timedelta(seconds=step):
    dateFrom = date
    dateTo = date + timedelta(seconds=step)
    data = downloader.get_data_from_oanda_fx(oanda, conf.insName, 'S{0}'.format(timeStep),
                                             dateFrom, dateTo)
    if len(data.get('candles')) > 0:
        cmd = ''
        cmd = ('INSERT INTO {0} VALUES').format(tName)
        cmd_bulk = ''
        for candle in data.get('candles'):
            id = parse_date(candle.get('time'))
            # add missing dates (when price does not change)
            if last_id != datetime.min:
                md = last_id + timedelta(seconds=timeStep)
                while md <= id:
                    if last_id != md:
                        volume = candle.get('volume')
                        if (md != id):
                            volume = 0
                        cmd_bulk = cmd_bulk + ("(TIMESTAMP '{0}',{1},{2},{3}),\n"
                                           .format(md, candle.get('ask')['c'], candle.get('bid')['c'],
                                                   volume))
                    md = md + timedelta(seconds=timeStep)
            last_id = id
        cmd = cmd + cmd_bulk[:-2] + ';'
        cursor.execute(cmd)
        connect.commit()
    print ("Saved candles from {0} to {1}".format(dateFrom, dateTo))
    date = dateTo

cmd = "REINDEX INDEX timestamp_idx;"
print cmd
cursor.execute(cmd)
connect.commit()

connect.close()
