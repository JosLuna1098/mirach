import 'package:flutter_test/flutter_test.dart';

import 'package:mirach_mobile/main.dart';

void main() {
  testWidgets('App renders without crashing', (WidgetTester tester) async {
    await tester.pumpWidget(const MirachApp());
    // The startup router shows a progress indicator while reading secure storage.
    expect(find.byType(MirachApp), findsOneWidget);
  });
}
