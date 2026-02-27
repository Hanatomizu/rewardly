import pandas as pd
import sqlite3
from werkzeug.security import generate_password_hash

def main():
    df = pd.read_excel("names.xlsx")
    conn = sqlite3.connect("rewardly.db")
    c = conn.cursor()
    print(df)
    for i in range(len(df)):
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  (df.at[i, "Name"], generate_password_hash(str(df.at[i, "Password"])), df.at[i, "Role"]) )
    conn.commit()
    conn.close()

if __name__ == '__main__':
    main()