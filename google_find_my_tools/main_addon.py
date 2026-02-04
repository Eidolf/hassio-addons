import sys
from Auth.adm_token_retrieval import get_adm_token
from Auth.username_provider import get_username
from NovaApi.ListDevices.nbe_list_devices import request_device_list
from ProtoDecoders.decoder import parse_device_list_protobuf, get_canonic_ids
from SpotApi.UploadPrecomputedPublicKeyIds.upload_precomputed_public_key_ids import refresh_custom_trackers
from NovaApi.ExecuteAction.LocateTracker.location_request import get_location_data_for_device

def main():
    print("[Add-on] Starting Authentication Flow...")
    try:
        # Step 1: Get Account Token (First Login)
        print("[Add-on] Step 1: Retrieving Account Token...")
        get_adm_token(get_username())
        print("[Add-on] Account Token retrieved successfully.")
        
        # Step 2: List Devices
        print("[Add-on] Step 2: Retrieving Device List...")
        result_hex = request_device_list()
        device_list = parse_device_list_protobuf(result_hex)
        refresh_custom_trackers(device_list)
        canonic_ids = get_canonic_ids(device_list)
        
        if not canonic_ids:
            print("[Add-on] No devices found on your account. Cannot proceed with second login.")
            print("[Add-on] Please ensure you have at least one device in 'Find My Device'.")
            sys.exit(1)
            
        print(f"[Add-on] Found {len(canonic_ids)} devices.")
        
        # Step 3: Select First Device and Request Location (Second Login)
        selected_device_name = canonic_ids[0][0]
        selected_canonic_id = canonic_ids[0][1]
        
        print(f"[Add-on] Step 3: Automatically selecting first device '{selected_device_name}' to trigger second login flow...")
        get_location_data_for_device(selected_canonic_id, selected_device_name)
        
        print("[Add-on] Full authentication flow completed.")
        print("[Add-on] Secrets should now be fully generated in Auth/secrets.json.")
        print("[Add-on] Exiting python script to allow secrets copying...")
        sys.exit(0)
        
    except Exception as e:
        print(f"[Add-on] An error occurred during the flow: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
