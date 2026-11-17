"""Tables. The same few operations over DynamoDB (deployed) or SQLite (on your laptop).

Every item is a dict with an "id". Each table keeps a "version" on every item, so a write
can be made conditional on what was read:

    t = table("runs")
    t.put_if_absent({"id": "refund:ch_7731", ...})   -> True if written, False if the id exists
    t.update_if({"id": run_id, ...}, version=6)      -> True if the item was still at version 6

STORE=local (the default off AWS) keeps tables in data/state/<prefix><name>.db.
STORE=dynamodb uses tables named <TABLE_PREFIX><name>; deploy.sh creates them.
"""
import json, os, sqlite3, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = os.environ.get("TABLE_PREFIX", "p3-")
TABLES = ["refunds", "runs", "approvals", "recordings", "crashes"]


def backend():
    if os.environ.get("STORE"):
        return os.environ["STORE"]
    return "dynamodb" if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else "local"


def table(name):
    return DynamoTable(name) if backend() == "dynamodb" else LocalTable(name)


class LocalTable:
    _lock = threading.Lock()

    def __init__(self, name):
        folder = os.environ.get("STATE_DIR", os.path.join(ROOT, "data", "state"))
        os.makedirs(folder, exist_ok=True)
        self.conn = sqlite3.connect(os.path.join(folder, PREFIX + name + ".db"), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, version INTEGER, body TEXT)")
        self.conn.commit()

    def get(self, id):
        row = self.conn.execute("SELECT version, body FROM items WHERE id = ?", (id,)).fetchone()
        return {**json.loads(row[1]), "version": row[0]} if row else None

    def put(self, item):
        with self._lock:
            old = self.get(item["id"])
            version = (old["version"] + 1) if old else 1
            self.conn.execute("INSERT OR REPLACE INTO items VALUES (?, ?, ?)", (item["id"], version, json.dumps(item)))
            self.conn.commit()
        return version

    def put_if_absent(self, item):
        with self._lock:
            try:
                self.conn.execute("INSERT INTO items VALUES (?, 1, ?)", (item["id"], json.dumps(item)))
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                self.conn.rollback()                 # release the write lock the failed insert took
                return False

    def update_if(self, item, version):
        with self._lock:
            cur = self.conn.execute("UPDATE items SET version = ?, body = ? WHERE id = ? AND version = ?",
                                    (version + 1, json.dumps(item), item["id"], version))
            self.conn.commit()
            return cur.rowcount == 1

    def scan(self, prefix=""):
        rows = self.conn.execute("SELECT version, body FROM items WHERE id LIKE ? ORDER BY id", (prefix + "%",))
        return [{**json.loads(b), "version": v} for v, b in rows]

    def clear(self):
        with self._lock:
            self.conn.execute("DELETE FROM items")
            self.conn.commit()


class DynamoTable:
    def __init__(self, name):
        import boto3
        self.t = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1")).Table(PREFIX + name)

    def get(self, id):
        r = self.t.get_item(Key={"id": id}, ConsistentRead=True).get("Item")
        return {**json.loads(r["body"]), "version": int(r["version"])} if r else None

    def put(self, item):
        old = self.get(item["id"])
        version = (old["version"] + 1) if old else 1
        self.t.put_item(Item={"id": item["id"], "version": version, "body": json.dumps(item)})
        return version

    def put_if_absent(self, item):
        from botocore.exceptions import ClientError
        try:
            self.t.put_item(Item={"id": item["id"], "version": 1, "body": json.dumps(item)},
                            ConditionExpression="attribute_not_exists(#k)", ExpressionAttributeNames={"#k": "id"})
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def update_if(self, item, version):
        from botocore.exceptions import ClientError
        try:
            self.t.put_item(Item={"id": item["id"], "version": version + 1, "body": json.dumps(item)},
                            ConditionExpression="#v = :v", ExpressionAttributeNames={"#v": "version"},
                            ExpressionAttributeValues={":v": version})
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def scan(self, prefix=""):
        items, kwargs = [], {"ConsistentRead": True}
        while True:
            page = self.t.scan(**kwargs)
            items += [i for i in page["Items"] if i["id"].startswith(prefix)]
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        return sorted(({**json.loads(i["body"]), "version": int(i["version"])} for i in items), key=lambda i: i["id"])

    def clear(self):
        with self.t.batch_writer() as b:
            for i in self.t.scan(ProjectionExpression="#k", ExpressionAttributeNames={"#k": "id"})["Items"]:
                b.delete_item(Key={"id": i["id"]})
