FROM python:3.8

# Copy current sources
COPY . /src

# install bets
RUN pip install /src

# install all possibly dependencies for plugins
RUN pip install pigar
RUN pigar -p /src/plugins-requirements.txt -P /src
RUN pip install -r /src/plugins-requirements.txt

# Install some 3rd party plugins
RUN pip install beets-artistcountry
RUN pip install beets-copyartifacts3
RUN pip install git+git://github.com/geigerzaehler/beets-check.git@master
RUN pip install beets-alternatives
RUN pip install beets-follow
RUN pip install beets-noimport
RUN pip install pip install git+git://github.com/igordertigor/beets-usertag.git@master
RUN pip install pip install git+git://github.com/8h2a/beets-barcode.git@master
RUN pip install beets-ydl
# some well known dependencies
RUN pip install pylast
RUN pip install flask
RUN pip install flask
RUN pip install beautifulsoup4

# remove sources
RUN rm -rf /src

# run everything under defined user
ARG APP_USER=beet
RUN groupadd -r ${APP_USER} && useradd --no-log-init -r -g ${APP_USER} -d /${APP_USER} ${APP_USER}
RUN mkdir -p /${APP_USER}
RUN chown ${APP_USER}:${APP_USER} /${APP_USER}

USER ${APP_USER}:${APP_USER}

# move /beet to volume and ask beet to use /beet as work directory
VOLUME /beet
ENV BEETSDIR=/beet

ENTRYPOINT ["beet"]
