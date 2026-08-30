import 'package:flutter/material.dart';

class RoleSelector extends StatelessWidget {
  const RoleSelector({
    super.key,
    required this.value,
    required this.onChanged,
  });

  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('I am a', style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _RoleCard(
                  label: 'Farmer',
                  icon: Icons.grass,
                  selected: value == 'farmer',
                  onTap: () => onChanged('farmer'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _RoleCard(
                  label: 'Buyer',
                  icon: Icons.storefront_outlined,
                  selected: value == 'buyer',
                  onTap: () => onChanged('buyer'),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _RoleCard(
                  label: 'Rider',
                  icon: Icons.delivery_dining,
                  selected: value == 'rider',
                  onTap: () => onChanged('rider'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RoleCard extends StatelessWidget {
  const _RoleCard({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Material(
      color: selected ? primary.withValues(alpha: 0.08) : null,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: selected ? primary : Theme.of(context).colorScheme.outline,
          width: selected ? 2 : 1,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
          child: Column(
            children: [
              Icon(icon, color: selected ? primary : null, size: 22),
              const SizedBox(height: 6),
              Text(
                label,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                  color: selected ? primary : null,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
