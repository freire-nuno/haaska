FROM public.ecr.aws/lambda/python:3.12

RUN yum install -y jq zip && yum clean all

RUN pip install awscli

RUN mkdir -p /usr/src/app

COPY . /usr/src/app
WORKDIR /usr/src/app

CMD ["make"]
