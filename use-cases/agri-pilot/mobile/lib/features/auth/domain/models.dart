class UserProfile {
  UserProfile({
    this.location,
    this.district,
    this.preferredLanguage,
    this.businessName,
    this.contactPhone,
    this.addressLabel,
    this.latitude,
    this.longitude,
    this.hasVehicle,
    this.isOnline,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) => UserProfile(
        location: json['location'] as String?,
        district: json['district'] as String?,
        preferredLanguage: json['preferred_language'] as String?,
        businessName: json['business_name'] as String?,
        contactPhone: json['contact_phone'] as String?,
        addressLabel: json['address_label'] as String?,
        latitude: json['latitude'] != null ? (json['latitude'] as num).toDouble() : null,
        longitude: json['longitude'] != null ? (json['longitude'] as num).toDouble() : null,
        hasVehicle: json['has_vehicle'] as bool?,
        isOnline: json['is_online'] as bool?,
      );

  final String? location;
  final String? district;
  final String? preferredLanguage;
  final String? businessName;
  final String? contactPhone;
  final String? addressLabel;
  final double? latitude;
  final double? longitude;
  final bool? hasVehicle;
  final bool? isOnline;
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
  bool get isRider => role == 'rider';
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
    this.plantId,
    required this.createdAt,
  });

  factory Listing.fromJson(Map<String, dynamic> json) => Listing(
        id: json['id'] as int,
        farmerId: json['farmer_id'] as int,
        crop: json['crop'] as String,
        quantityKg: (json['quantity_kg'] as num).toDouble(),
        pricePerKg: json['price_per_kg'] != null ? (json['price_per_kg'] as num).toDouble() : null,
        status: json['status'] as String,
        plantId: json['plant_id'] as int?,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  final int id;
  final int farmerId;
  final String crop;
  final double quantityKg;
  final double? pricePerKg;
  final String status;
  final int? plantId;
  final DateTime createdAt;

  bool get isTracked => plantId != null;
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

class ThreadSummary {
  ThreadSummary({
    required this.sessionId,
    required this.name,
    required this.updatedAt,
  });

  factory ThreadSummary.fromJson(Map<String, dynamic> json) => ThreadSummary(
        sessionId: json['session_id'] as String,
        name: (json['name'] as String?)?.trim().isNotEmpty == true ? json['name'] as String : 'Conversation',
        updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ??
            DateTime.tryParse(json['created_at'] as String? ?? '') ??
            DateTime.now(),
      );

  final String sessionId;
  final String name;
  final DateTime updatedAt;
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

class ScanPrediction {
  ScanPrediction({required this.label, required this.confidence});

  factory ScanPrediction.fromJson(Map<String, dynamic> json) => ScanPrediction(
        label: json['label'] as String,
        confidence: (json['confidence'] as num).toDouble(),
      );

  final String label;
  final double confidence;
}

class ScanResult {
  ScanResult({
    required this.qualityOk,
    this.qualityReason,
    required this.predictions,
    this.topLabel,
    this.topConfidence,
    required this.confident,
    this.adviceSummary,
  });

  factory ScanResult.fromJson(Map<String, dynamic> json) => ScanResult(
        qualityOk: json['quality_ok'] as bool,
        qualityReason: json['quality_reason'] as String?,
        predictions: (json['predictions'] as List<dynamic>? ?? [])
            .map((e) => ScanPrediction.fromJson(e as Map<String, dynamic>))
            .toList(),
        topLabel: json['top_label'] as String?,
        topConfidence: json['top_confidence'] != null ? (json['top_confidence'] as num).toDouble() : null,
        confident: json['confident'] as bool? ?? false,
        adviceSummary: json['advice_summary'] as String?,
      );

  final bool qualityOk;
  final String? qualityReason;
  final List<ScanPrediction> predictions;
  final String? topLabel;
  final double? topConfidence;
  final bool confident;
  final String? adviceSummary;
}

class PlantSummary {
  PlantSummary({
    required this.id,
    required this.crop,
    required this.name,
    this.plantedOn,
    this.listingId,
    required this.observationCount,
    this.latestLabel,
    required this.trend,
    required this.createdAt,
    required this.updatedAt,
  });

  factory PlantSummary.fromJson(Map<String, dynamic> json) => PlantSummary(
        id: json['id'] as int,
        crop: json['crop'] as String,
        name: json['name'] as String,
        plantedOn: json['planted_on'] != null ? DateTime.parse(json['planted_on'] as String) : null,
        listingId: json['listing_id'] as int?,
        observationCount: json['observation_count'] as int? ?? 0,
        latestLabel: json['latest_label'] as String?,
        trend: json['trend'] as String? ?? 'unknown',
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
      );

  final int id;
  final String crop;
  final String name;
  final DateTime? plantedOn;
  final int? listingId;
  final int observationCount;
  final String? latestLabel;
  final String trend;
  final DateTime createdAt;
  final DateTime updatedAt;
}

class PlantObservation {
  PlantObservation({
    required this.id,
    required this.plantId,
    required this.capturedAt,
    required this.qualityOk,
    this.qualityReason,
    this.topLabel,
    this.topConfidence,
    this.adviceSummary,
    required this.source,
    this.photoUrl,
  });

  factory PlantObservation.fromJson(Map<String, dynamic> json) => PlantObservation(
        id: json['id'] as int,
        plantId: json['plant_id'] as int,
        capturedAt: DateTime.parse(json['captured_at'] as String),
        qualityOk: json['quality_ok'] as bool,
        qualityReason: json['quality_reason'] as String?,
        topLabel: json['top_label'] as String?,
        topConfidence: json['top_confidence'] != null ? (json['top_confidence'] as num).toDouble() : null,
        adviceSummary: json['advice_summary'] as String?,
        source: json['source'] as String,
        photoUrl: json['photo_url'] as String?,
      );

  final int id;
  final int plantId;
  final DateTime capturedAt;
  final bool qualityOk;
  final String? qualityReason;
  final String? topLabel;
  final double? topConfidence;
  final String? adviceSummary;
  final String source;
  final String? photoUrl;
}

class PlantInsights {
  PlantInsights({
    required this.crop,
    required this.observationCount,
    this.firstObservationDate,
    this.lastObservationDate,
    this.latestLabel,
    this.latestConfidence,
    required this.timeline,
    required this.trend,
  });

  factory PlantInsights.fromJson(Map<String, dynamic> json) => PlantInsights(
        crop: json['crop'] as String,
        observationCount: json['observation_count'] as int? ?? 0,
        firstObservationDate: json['first_observation_date'] as String?,
        lastObservationDate: json['last_observation_date'] as String?,
        latestLabel: json['latest_label'] as String?,
        latestConfidence: json['latest_confidence'] != null ? (json['latest_confidence'] as num).toDouble() : null,
        timeline: (json['timeline'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>(),
        trend: json['trend'] as String? ?? 'unknown',
      );

  final String crop;
  final int observationCount;
  final String? firstObservationDate;
  final String? lastObservationDate;
  final String? latestLabel;
  final double? latestConfidence;
  final List<Map<String, dynamic>> timeline;
  final String trend;
}

class PlantDetail {
  PlantDetail({
    required this.id,
    required this.crop,
    required this.name,
    this.plantedOn,
    this.listingId,
    required this.createdAt,
    required this.updatedAt,
    required this.observations,
    required this.insights,
  });

  factory PlantDetail.fromJson(Map<String, dynamic> json) => PlantDetail(
        id: json['id'] as int,
        crop: json['crop'] as String,
        name: json['name'] as String,
        plantedOn: json['planted_on'] != null ? DateTime.parse(json['planted_on'] as String) : null,
        listingId: json['listing_id'] as int?,
        createdAt: DateTime.parse(json['created_at'] as String),
        updatedAt: DateTime.parse(json['updated_at'] as String),
        observations: (json['observations'] as List<dynamic>? ?? [])
            .map((e) => PlantObservation.fromJson(e as Map<String, dynamic>))
            .toList(),
        insights: PlantInsights.fromJson(json['insights'] as Map<String, dynamic>),
      );

  final int id;
  final String crop;
  final String name;
  final DateTime? plantedOn;
  final int? listingId;
  final DateTime createdAt;
  final DateTime updatedAt;
  final List<PlantObservation> observations;
  final PlantInsights insights;
}

class ListingInsights {
  ListingInsights({
    required this.listingId,
    required this.plantId,
    required this.crop,
    required this.observationCount,
    this.firstObservationDate,
    this.lastObservationDate,
    this.latestLabel,
    this.latestConfidence,
    required this.timeline,
    required this.trend,
  });

  factory ListingInsights.fromJson(Map<String, dynamic> json) => ListingInsights(
        listingId: json['listing_id'] as int,
        plantId: json['plant_id'] as int,
        crop: json['crop'] as String,
        observationCount: json['observation_count'] as int? ?? 0,
        firstObservationDate: json['first_observation_date'] as String?,
        lastObservationDate: json['last_observation_date'] as String?,
        latestLabel: json['latest_label'] as String?,
        latestConfidence: json['latest_confidence'] != null ? (json['latest_confidence'] as num).toDouble() : null,
        timeline: (json['timeline'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>(),
        trend: json['trend'] as String? ?? 'unknown',
      );

  final int listingId;
  final int plantId;
  final String crop;
  final int observationCount;
  final String? firstObservationDate;
  final String? lastObservationDate;
  final String? latestLabel;
  final double? latestConfidence;
  final List<Map<String, dynamic>> timeline;
  final String trend;
}

class OrderItem {
  OrderItem({
    required this.id,
    required this.connectionId,
    required this.listingId,
    required this.crop,
    required this.quantityKg,
    required this.fulfillmentMode,
    required this.status,
    this.pricePerKg,
    this.deliveryId,
    this.deliveryStatus,
    this.pickupAddressLabel,
    this.deliveryAddressLabel,
  });

  factory OrderItem.fromJson(Map<String, dynamic> json) => OrderItem(
        id: json['id'] as int,
        connectionId: json['connection_id'] as int,
        listingId: json['listing_id'] as int,
        crop: json['crop'] as String,
        quantityKg: (json['quantity_kg'] as num).toDouble(),
        fulfillmentMode: json['fulfillment_mode'] as String,
        status: json['status'] as String,
        pricePerKg: json['price_per_kg'] != null ? (json['price_per_kg'] as num).toDouble() : null,
        deliveryId: json['delivery_id'] as int?,
        deliveryStatus: json['delivery_status'] as String?,
        pickupAddressLabel: json['pickup_address_label'] as String?,
        deliveryAddressLabel: json['delivery_address_label'] as String?,
      );

  final int id;
  final int connectionId;
  final int listingId;
  final String crop;
  final double quantityKg;
  final String fulfillmentMode;
  final String status;
  final double? pricePerKg;
  final int? deliveryId;
  final String? deliveryStatus;
  final String? pickupAddressLabel;
  final String? deliveryAddressLabel;
}

class OrderCreateResult {
  OrderCreateResult({required this.order, required this.handoffPin});

  factory OrderCreateResult.fromJson(Map<String, dynamic> json) => OrderCreateResult(
        order: OrderItem.fromJson(json['order'] as Map<String, dynamic>),
        handoffPin: json['handoff_pin'] as String,
      );

  final OrderItem order;
  final String handoffPin;
}

class OrderTracking {
  OrderTracking({
    required this.orderId,
    required this.status,
    required this.fulfillmentMode,
    required this.quantityKg,
    required this.crop,
    required this.pickup,
    required this.delivery,
    required this.rider,
    this.deliveryStatus,
    required this.events,
  });

  factory OrderTracking.fromJson(Map<String, dynamic> json) => OrderTracking(
        orderId: json['order_id'] as int,
        status: json['status'] as String,
        fulfillmentMode: json['fulfillment_mode'] as String,
        quantityKg: (json['quantity_kg'] as num).toDouble(),
        crop: json['crop'] as String,
        pickup: json['pickup'] as Map<String, dynamic>,
        delivery: json['delivery'] as Map<String, dynamic>,
        rider: json['rider'] as Map<String, dynamic>,
        deliveryStatus: json['delivery_status'] as String?,
        events: (json['events'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>(),
      );

  final int orderId;
  final String status;
  final String fulfillmentMode;
  final double quantityKg;
  final String crop;
  final Map<String, dynamic> pickup;
  final Map<String, dynamic> delivery;
  final Map<String, dynamic> rider;
  final String? deliveryStatus;
  final List<Map<String, dynamic>> events;
}

class RiderJob {
  RiderJob({
    required this.orderId,
    required this.deliveryId,
    required this.crop,
    required this.quantityKg,
    required this.pickupDistrictArea,
    required this.deliveryDistrictArea,
    required this.distanceToPickupKm,
    required this.routeDistanceM,
    required this.routeDurationS,
    required this.mapsAvailable,
  });

  factory RiderJob.fromJson(Map<String, dynamic> json) => RiderJob(
        orderId: json['order_id'] as int,
        deliveryId: json['delivery_id'] as int,
        crop: json['crop'] as String,
        quantityKg: (json['quantity_kg'] as num).toDouble(),
        pickupDistrictArea: json['pickup_district_area'] as String,
        deliveryDistrictArea: json['delivery_district_area'] as String,
        distanceToPickupKm: (json['distance_to_pickup_km'] as num).toDouble(),
        routeDistanceM: json['route_distance_m'] as int,
        routeDurationS: json['route_duration_s'] as int,
        mapsAvailable: json['maps_available'] as bool? ?? false,
      );

  final int orderId;
  final int deliveryId;
  final String crop;
  final double quantityKg;
  final String pickupDistrictArea;
  final String deliveryDistrictArea;
  final double distanceToPickupKm;
  final int routeDistanceM;
  final int routeDurationS;
  final bool mapsAvailable;
}
