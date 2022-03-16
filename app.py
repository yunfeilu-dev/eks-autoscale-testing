from flask import Flask
import math
app = Flask(__name__)

@app.route('/')
def hello_world():
    x = 0.0001
    for i in range(1000000):
        x += math.sqrt(x)
    return 'Hello, Docker!'

