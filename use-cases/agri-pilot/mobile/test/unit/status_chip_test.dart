import 'package:agripilot_mobile/core/widgets/status_chip.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('orderStatusLabel maps pending_farmer_confirmation', () {
    expect(orderStatusLabel('pending_farmer_confirmation'), 'Waiting for farm');
  });

  test('orderStatusLabel maps searching_rider', () {
    expect(orderStatusLabel('searching_rider'), 'Finding rider');
  });

  test('orderStatusLabel maps rider_assigned', () {
    expect(orderStatusLabel('rider_assigned'), 'Rider assigned');
  });
}
