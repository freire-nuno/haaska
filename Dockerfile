FROM amazonlinux:2023

RUN dnf install -y python3.12 python3.12-pip jq zip make && dnf clean all

RUN pip3.12 install awscli

RUN mkdir -p /usr/src/app

COPY . /usr/src/app
WORKDIR /usr/src/app

CMD ["make"]
