class UserProfile {
  UserProfile({
    this.location,
    this.district,
    this.preferredLanguage,
    this.businessName,
    this.contactPhone,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) => UserProfile(
        location: json['location'] as String?,
        district: json['district'] as String?,
        preferredLanguage: json['preferred_language'] as String?,
        businessName: json['business_name'] as String?,
        contactPhone: json['contact_phone'] as String?,
      );

  final String? location;
  final String? district;
  final String? preferredLanguage;
  final String? businessName;
  final String? contactPhone;
}

class UserMe {
  UserMe({
    required this.id,
    required this.phoneNumber,
    required this.role,
    required this.subscriptionStatus,
    required this.name,
    required this.createdAt,
    this.profile,
  });

  factory UserMe.fromJson(Map<String, dynamic> json) => UserMe(
        id: json['id'] as int,
        phoneNumber: json['phone_number'] as String,
        role: json['role'] as String,
        subscriptionStatus: json['subscription_status'] as String,
        name: json['name'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        profile: json['profile'] != null ? UserProfile.fromJson(json['profile'] as Map<String, dynamic>) : null,
      );

  final int id;
  final String phoneNumber;
  final String role;
  final String subscriptionStatus;
  final String name;
  final DateTime createdAt;
  final UserProfile? profile;

  bool get isFarmer => role == 'farmer';
  bool get isBuyer => role == 'buyer';
  bool get isActiveFarmer => isFarmer && subscriptionStatus == 'active';
}

class Listing {
  Listing({
    required this.id,
    required this.farmerId,
    required this.crop,
    required this.quantityKg,
    this.pricePerKg,
    required this.status,
    required this.createdAt,
  });

  factory Listing.fromJson(Map<String, dynamic> json) => Listing(
        id: json['id'] as int,
        farmerId: json['farmer_id'] as int,
        crop: json['crop'] as String,
        quantityKg: (json['quantity_kg'] as num).toDouble(),
        pricePerKg: json['price_per_kg'] != null ? (json['price_per_kg'] as num).toDouble() : null,
        status: json['status'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  final int id;
  final int farmerId;
  final String crop;
  final double quantityKg;
  final double? pricePerKg;
  final String status;
  final DateTime createdAt;
}

class ConnectionItem {
  ConnectionItem({
    required this.id,
    required this.listingId,
    required this.status,
    required this.listing,
    this.message,
  });

  factory ConnectionItem.fromJson(Map<String, dynamic> json) => ConnectionItem(
        id: json['id'] as int,
        listingId: json['listing_id'] as int,
        status: json['status'] as String,
        message: json['message'] as String?,
        listing: Listing.fromJson(json['listing'] as Map<String, dynamic>),
      );

  final int id;
  final int listingId;
  final String status;
  final String? message;
  final Listing listing;
}

class ChatMessage {
  ChatMessage({required this.role, required this.content, required this.createdAt});
  final String role;
  final String content;
  final DateTime createdAt;
}

class ChannelsStatus {
  ChannelsStatus({required this.telegramLinked, required this.telegramEligible, required this.whatsappEligible});

  factory ChannelsStatus.fromJson(Map<String, dynamic> json) {
    final tg = json['telegram'] as Map<String, dynamic>;
    final wa = json['whatsapp'] as Map<String, dynamic>;
    return ChannelsStatus(
      telegramLinked: tg['linked'] as bool,
      telegramEligible: tg['eligible'] as bool,
      whatsappEligible: wa['eligible'] as bool,
    );
  }

  final bool telegramLinked;
  final bool telegramEligible;
  final bool whatsappEligible;
}

class PublicConfig {
  PublicConfig({this.whatsappWaMe, this.telegramDeepLinkBase, this.signupUrl});

  factory PublicConfig.fromJson(Map<String, dynamic> json) => PublicConfig(
        whatsappWaMe: json['whatsapp_wa_me'] as String?,
        telegramDeepLinkBase: json['telegram_deep_link_base'] as String?,
        signupUrl: json['signup_url'] as String?,
      );

  final String? whatsappWaMe;
  final String? telegramDeepLinkBase;
  final String? signupUrl;
}
