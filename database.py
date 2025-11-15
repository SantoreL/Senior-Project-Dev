import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="password",
        database="MusicToolbox"
    )

def insert_data(data):
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        INSERT INTO songs (
            name, 
            artist, 
            album, 
            release_date, 
            length, 
            cover_url, 
            publisher, 
            cr_year, 
            license,
            copyright
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    values = (
        data['name'],
        data['artist'],
        data['album'],
        data['release_date'],
        data['length'],
        data['cover_url'],
        data['publisher'],
        data['cr_year'],
        data['license'],
        data['copyright']
    )

    cursor.execute(sql, values)
    conn.commit()

    cursor.close()
    conn.close()