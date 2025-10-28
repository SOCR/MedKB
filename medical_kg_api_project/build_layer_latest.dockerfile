FROM public.ecr.aws/lambda/python:3.11

# Copy requirements file
COPY requirements_layer_latest.txt /requirements.txt

# Install Python packages
RUN pip install --no-cache-dir -r /requirements.txt -t /opt/python/

# Create the layer structure
RUN mkdir -p /opt/layer/python
RUN cp -r /opt/python/* /opt/layer/python/

# Set the working directory for the layer content
WORKDIR /opt/layer 