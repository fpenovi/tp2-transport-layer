from server.operations.upload_operation import UploadOperation
from server.operations.download_operation import DownloadOperation
from server.operations.operations_chain import OperationsChain


def start_server(server_address, storage_dir, server_class):
    chain = OperationsChain(UploadOperation, DownloadOperation)
    server = None

    try:
        server = server_class(server_address, storage_dir, chain)
        server.start()
    except RuntimeError as e:
        return print(str(e))
    except (KeyboardInterrupt, SystemExit):
        print(f'\nShutting down gracefully...\n')
        server and server.shutdown()
