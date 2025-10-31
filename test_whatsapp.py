#!/usr/bin/env python3
"""
Test script for WhatsApp Click-to-Chat links
"""
import sys
from src.notifications import generate_whatsapp_link, pair_buyer_seller

def test_whatsapp_links():
    """Test WhatsApp link generation functions"""

    print("Testing WhatsApp Click-to-Chat Link Generation...")
    print("=" * 60)

    # Test basic link generation
    test_number = "+50948592888"
    print(f"📱 Testing basic link for {test_number}...")
    basic_link = generate_whatsapp_link(test_number)
    expected_basic = "https://wa.me/50948592888"
    if basic_link == expected_basic:
        print("✅ Basic link generated correctly")
        print(f"   Link: {basic_link}")
    else:
        print("❌ Basic link failed")
        print(f"   Expected: {expected_basic}")
        print(f"   Got: {basic_link}")
        return False

    # Test link with message
    test_message = "Hello, this is a test message!"
    print(f"\n💬 Testing link with message for {test_number}...")
    message_link = generate_whatsapp_link(test_number, test_message)
    if message_link and "text=" in message_link:
        print("✅ Message link generated correctly")
        print(f"   Link: {message_link}")
    else:
        print("❌ Message link failed")
        return False

    # Test buyer-seller pairing
    buyer_whatsapp = "+50940000000"
    seller_whatsapp = "+50948592888"
    ad_title = "Test Advertisement"
    delivery_id = "test-delivery-123"

    print(f"\n👥 Testing buyer-seller pairing...")
    print(f"   Buyer: {buyer_whatsapp}")
    print(f"   Seller: {seller_whatsapp}")
    print(f"   Ad: {ad_title}")

    pairing_result = pair_buyer_seller(buyer_whatsapp, seller_whatsapp, ad_title, delivery_id)

    if pairing_result and 'buyer_contact_link' in pairing_result and 'seller_contact_link' in pairing_result:
        print("✅ Buyer-seller pairing successful")
        print(f"   Buyer contact link: {pairing_result['buyer_contact_link']}")
        print(f"   Seller contact link: {pairing_result['seller_contact_link']}")
    else:
        print("❌ Buyer-seller pairing failed")
        return False

    # Test edge cases
    print(f"\n🔧 Testing edge cases...")

    # Test with number without +
    number_no_plus = "50948592888"
    link_no_plus = generate_whatsapp_link(number_no_plus)
    if link_no_plus == "https://wa.me/50948592888":
        print("✅ Number without + handled correctly")
    else:
        print("❌ Number without + failed")
        return False

    # Test with invalid number
    invalid_number = "invalid"
    invalid_link = generate_whatsapp_link(invalid_number)
    if invalid_link:
        print("✅ Invalid number handled gracefully")
    else:
        print("❌ Invalid number not handled properly")
        return False

    print("\n🎉 All WhatsApp link generation tests passed!")
    print("📋 Summary:")
    print("   - Basic wa.me links work correctly")
    print("   - Links with pre-filled messages work")
    print("   - Buyer-seller pairing generates proper contact links")
    print("   - Edge cases handled appropriately")
    print("\n🔗 Example usage:")
    print(f"   generate_whatsapp_link('+50948592888') -> {generate_whatsapp_link('+50948592888')}")
    print(f"   generate_whatsapp_link('+50948592888', 'Hello!') -> {generate_whatsapp_link('+50948592888', 'Hello!')}")

    return True

if __name__ == "__main__":
    print("WhatsApp Click-to-Chat Link Testing")
    print("=" * 60)

    success = test_whatsapp_links()

    if success:
        print("\n✅ All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Check the output above.")
        sys.exit(1)
