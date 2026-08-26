// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'job_page.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

JobPage _$JobPageFromJson(Map<String, dynamic> json) => $checkedCreate(
  'JobPage',
  json,
  ($checkedConvert) {
    $checkKeys(json, requiredKeys: const ['items', 'total', 'limit', 'offset']);
    final val = JobPage(
      items: $checkedConvert(
        'items',
        (v) => (v as List<dynamic>)
            .map((e) => JobStatus.fromJson(e as Map<String, dynamic>))
            .toList(),
      ),
      total: $checkedConvert('total', (v) => (v as num).toInt()),
      limit: $checkedConvert('limit', (v) => (v as num).toInt()),
      offset: $checkedConvert('offset', (v) => (v as num).toInt()),
    );
    return val;
  },
);

Map<String, dynamic> _$JobPageToJson(JobPage instance) => <String, dynamic>{
  'items': instance.items.map((e) => e.toJson()).toList(),
  'total': instance.total,
  'limit': instance.limit,
  'offset': instance.offset,
};
