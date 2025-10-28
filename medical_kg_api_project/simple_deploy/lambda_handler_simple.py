from mangum import Mangum
from main_simple import app

lambda_handler = Mangum(app, lifespan="off") 