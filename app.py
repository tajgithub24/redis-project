from flask import Flask, jsonify, request, render_template, redirect, url_for, flash
import pymssql
import redis
import json
from flask_caching import Cache
from config import Config
import logging

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = '7868ceaecf1ec1ba98a661334d51d60249693d37c8ddcb58'  # Needed for flashing messages

# Setup Redis caching
cache = Cache(app, config={
    'CACHE_TYPE': 'redis',
    'CACHE_REDIS_HOST': app.config['REDIS_HOST'],
    'CACHE_REDIS_PORT': app.config['REDIS_PORT'],
    'CACHE_REDIS_DB': app.config['REDIS_DB']
})

# Setup MSSQL connection
def get_mssql_connection():
    return pymssql.connect(
        server=app.config['SQL_SERVER'],
        user=app.config['SQL_USER'],
        password=app.config['SQL_PASSWORD'],
        database=app.config['SQL_DATABASE']
    )

# Setup Redis connection
def get_redis_connection():
    return redis.Redis(
        host=app.config['REDIS_HOST'],
        port=app.config['REDIS_PORT'],
        db=app.config['REDIS_DB']
    )

@app.route('/')
def index():
    search_query = request.args.get('search', '')
    cache_key = f'users:{search_query}'
    
    redis_conn = get_redis_connection()
    users = redis_conn.get(cache_key)
    if users is None:
        conn = get_mssql_connection()
        cursor = conn.cursor(as_dict=True)
        if search_query:
            cursor.execute("SELECT * FROM people WHERE name LIKE %s", (f'%{search_query}%',))
        else:
            cursor.execute("SELECT * FROM people")
        users = cursor.fetchall()
        conn.close()
        redis_conn.set(cache_key, json.dumps(users), ex=60)  # Set TTL of 60 minutes
        source = 'MSSQL'
    else:
        users = json.loads(users)
        source = 'Redis'

    return render_template('index.html', users=users, source=source)

@app.route('/add_person', methods=['GET', 'POST'])
def add_person():
    if request.method == 'POST':
        name = request.form.get('name')
        age = request.form.get('age')
        conn = get_mssql_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO people (name, age) VALUES (%s, %d)", (name, int(age)))
        conn.commit()
        conn.close()
        # Invalidate Redis cache
        redis_conn = get_redis_connection()
        for key in redis_conn.scan_iter('users:*'):
            redis_conn.delete(key)
        flash('Person added successfully!', 'success')
        return redirect(url_for('index'))
    return render_template('add_person.html')

@app.route('/edit_person/<int:id>', methods=['GET', 'POST'])
def edit_person(id):
    conn = get_mssql_connection()
    cursor = conn.cursor(as_dict=True)
    
    if request.method == 'POST':
        name = request.form.get('name')
        age = request.form.get('age')
        cursor.execute("UPDATE people SET name = %s, age = %d WHERE id = %d", (name, int(age), id))
        conn.commit()
        conn.close()
        # Invalidate Redis cache
        redis_conn = get_redis_connection()
        for key in redis_conn.scan_iter('users:*'):
            redis_conn.delete(key)
        flash('Person updated successfully!', 'success')
        return redirect(url_for('index'))

    cursor.execute("SELECT * FROM people WHERE id = %d", (id,))
    person = cursor.fetchone()
    conn.close()
    return render_template('edit_person.html', person=person)

@app.route('/confirm_delete/<int:id>', methods=['GET'])
def confirm_delete(id):
    conn = get_mssql_connection()
    cursor = conn.cursor(as_dict=True)
    cursor.execute("SELECT * FROM people WHERE id = %d", (id,))
    person = cursor.fetchone()
    conn.close()
    return render_template('delete_person.html', person=person)

@app.route('/delete_person_mssql/<int:id>', methods=['POST'])
def delete_person_mssql(id):
    conn = get_mssql_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM people WHERE id = %d", (id,))
    conn.commit()
    conn.close()
    # Invalidate Redis cache
    redis_conn = get_redis_connection()
    for key in redis_conn.scan_iter('users:*'):
        redis_conn.delete(key)
    flash('Person deleted from MSSQL successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/delete_person_redis/<int:id>', methods=['POST'])
def delete_person_redis(id):
    # Invalidate Redis cache for specific person
    redis_conn = get_redis_connection()
    cache_keys = redis_conn.scan_iter(f'users:{id}*')
    logging.debug(cache_keys)
    for key in cache_keys:
        redis_conn.delete(key)
    flash('Person deleted from Redis cache successfully!', 'success')
    return redirect(url_for('index'))





if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)

