import subprocess
import sys

START_KAFKA_CONNECT = ['sudo', 'supervisorctl', 'start', 'kafka-connect']


def write_stdout(s):
    # only eventlistener protocol messages may be sent to stdout
    sys.stdout.write(s)
    sys.stdout.flush()


def write_stderr(s):
    sys.stderr.write(s)
    sys.stderr.write('\n')
    sys.stderr.flush()


def main():
    while True:
        # transition from ACKNOWLEDGED to READY
        write_stdout('READY\n')

        # read header line and print it to stderr
        line = sys.stdin.readline()

        # read event payload and print it to stderr
        headers = dict([x.split(':') for x in line.split()])

        data = sys.stdin.read(int(headers['len']))
        body = dict([x.split(':') for x in data.split()])

        if body['processname'] == 'schema-registry':
            write_stderr(line)
            write_stderr(data)
            if headers['eventname'] == 'PROCESS_STATE_RUNNING':
                subprocess.call(START_KAFKA_CONNECT)

        # transition from READY to ACKNOWLEDGED
        write_stdout('RESULT 2\nOK')


if __name__ == '__main__':
    main()