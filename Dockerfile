FROM continuumio/miniconda3
ADD environment.yml /tmp/environment.yml
RUN conda env create -f /tmp/environment.yml
# Pull the environment name out of the environment.yml
RUN echo "source activate $(head -1 /environment.yml | cut -d' ' -f2)" > ~/.bashrc
ENV PATH="/opt/conda/envs/$(head -1 /environment.yml | cut -d' ' -f2)/bin:$PATH"

# Copy the project into the image
ADD /app /
SHELL ["conda", "run", "-n", "channel_layer", "/bin/bash", "-c"]
# Run with uvicorn
CMD ["conda", "run", "-n", "channel_layer", "--no-capture-output", "uvicorn", "channel_layer:app", "--host", "0.0.0.0", "--port", "9000"]