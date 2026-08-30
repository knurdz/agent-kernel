import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../auth/domain/models.dart';

class PlantMetricTile extends StatelessWidget {
  const PlantMetricTile({super.key, required this.label, required this.value, this.icon});

  final String label;
  final String value;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (icon != null) Icon(icon, size: 18, color: theme.colorScheme.primary),
            if (icon != null) const SizedBox(height: 6),
            Text(value, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text(label, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          ],
        ),
      ),
    );
  }
}

class PlantTrendChip extends StatelessWidget {
  const PlantTrendChip({super.key, required this.trend});

  final String trend;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (trend) {
      'improving' => ('Improving', Colors.green),
      'worsening' => ('Needs attention', Colors.orange),
      'stable' => ('Stable', Colors.blue),
      _ => ('Unknown', Colors.grey),
    };
    return Chip(
      label: Text(label, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
      backgroundColor: color.withValues(alpha: 0.15),
      side: BorderSide.none,
      visualDensity: VisualDensity.compact,
    );
  }
}

class PlantCareExpandable extends StatelessWidget {
  const PlantCareExpandable({super.key, required this.title, required this.body, this.icon});

  final String title;
  final String body;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    if (body.trim().isEmpty) return const SizedBox.shrink();
    return Card(
      child: ExpansionTile(
        leading: icon != null ? Icon(icon, color: Theme.of(context).colorScheme.primary) : null,
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Align(alignment: Alignment.centerLeft, child: Text(body)),
          ),
        ],
      ),
    );
  }
}

class PlantHealthChart extends StatelessWidget {
  const PlantHealthChart({super.key, required this.series});

  final List<HealthPoint> series;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (series.length < 2) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            'Add at least two clear photos to see health trends over time.',
            style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
      );
    }

    final spots = <FlSpot>[];
    for (var i = 0; i < series.length; i++) {
      spots.add(FlSpot(i.toDouble(), series[i].severity.toDouble()));
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 16, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Health over time', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            SizedBox(
              height: 160,
              child: LineChart(
                LineChartData(
                  minY: 0,
                  maxY: 3,
                  gridData: const FlGridData(show: true, drawVerticalLine: false),
                  titlesData: FlTitlesData(
                    leftTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 28,
                        getTitlesWidget: (value, _) {
                          final label = switch (value.toInt()) {
                            0 => 'OK',
                            1 => 'Mild',
                            2 => 'Mod',
                            3 => 'High',
                            _ => '',
                          };
                          return Text(label, style: theme.textTheme.labelSmall);
                        },
                      ),
                    ),
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 22,
                        interval: 1,
                        getTitlesWidget: (value, _) {
                          final idx = value.toInt();
                          if (idx < 0 || idx >= series.length) return const SizedBox.shrink();
                          final d = DateTime.tryParse(series[idx].date);
                          final text = d != null ? DateFormat('d/M').format(d) : '';
                          return Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text(text, style: theme.textTheme.labelSmall),
                          );
                        },
                      ),
                    ),
                    rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  ),
                  borderData: FlBorderData(show: false),
                  lineBarsData: [
                    LineChartBarData(
                      spots: spots,
                      isCurved: true,
                      color: theme.colorScheme.primary,
                      barWidth: 3,
                      dotData: const FlDotData(show: true),
                      belowBarData: BarAreaData(
                        show: true,
                        color: theme.colorScheme.primary.withValues(alpha: 0.12),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class PlantHarvestProgress extends StatelessWidget {
  const PlantHarvestProgress({super.key, required this.cropCare});

  final CropCare cropCare;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (cropCare.needsPlantedDate) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(Icons.calendar_today_outlined, color: theme.colorScheme.primary),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Set your plant date to see harvest countdown and growth progress.',
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ),
      );
    }

    final progress = (cropCare.growthProgress ?? 0).clamp(0.0, 1.0);
    final minLeft = cropCare.daysToHarvestMinRemaining;
    final maxLeft = cropCare.daysToHarvestMaxRemaining;
    final countdown = minLeft != null && maxLeft != null
        ? (minLeft == maxLeft ? '$minLeft days' : '$minLeft–$maxLeft days')
        : '—';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Days to harvest', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(countdown, style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
            if (cropCare.harvestWindowStart != null && cropCare.harvestWindowEnd != null) ...[
              const SizedBox(height: 4),
              Text(
                'Window: ${cropCare.harvestWindowStart} → ${cropCare.harvestWindowEnd}',
                style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: progress > 0 ? progress : null,
                minHeight: 10,
                backgroundColor: theme.colorScheme.surfaceContainerHighest,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              '${(progress * 100).round()}% through typical growth cycle',
              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

String formatDiagnosisLabel(String? label) {
  if (label == null) return '—';
  return label.replaceAll('___', ' · ').replaceAll('_', ' ');
}
