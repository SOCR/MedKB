FROM public.ecr.aws/lambda/python:3.11

# Create layer directory structure
RUN mkdir -p /opt/python

# Install our dependencies
COPY requirements_layer.txt /tmp/
RUN pip install -r /tmp/requirements_layer.txt -t /opt/python/

# Create the layer zip
WORKDIR /opt
CMD ["sh", "-c", "zip -r /tmp/layer.zip python/"] 