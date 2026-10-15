"""Focused assertions on reviewed security properties, alongside cfn-lint."""

from pathlib import Path

import yaml


class TemplateLoader(yaml.SafeLoader):
    pass


def intrinsic(loader, tag, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {tag: value}


TemplateLoader.add_multi_constructor("!", intrinsic)


def template():
    loader = TemplateLoader(Path("infra/template.yaml").read_text(encoding="utf-8"))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def test_function_role_has_only_prefix_read_and_scoped_log_writes():
    resources = template()["Resources"]
    role = resources["AnalyzerRole"]["Properties"]
    assert len(role["Policies"]) == 1
    read, logs = role["Policies"][0]["PolicyDocument"]["Statement"]
    assert read["Effect"] == logs["Effect"] == "Allow"
    assert read["Action"] == "s3:GetObject"
    assert read["Resource"] == {
        "Sub": "arn:${AWS::Partition}:s3:::${AWS::AccountId}-"
        "${AWS::Region}-lad-synthetic-input/incoming/*"
    }
    assert logs["Action"] == ["logs:CreateLogStream", "logs:PutLogEvents"]
    assert logs["Resource"] == {
        "Sub": "arn:${AWS::Partition}:logs:${AWS::Region}:"
        "${AWS::AccountId}:log-group:/aws/lambda/"
        "${FunctionName}:log-stream:*"
    }
    assert resources["Analyzer"]["Properties"]["Role"] == {"GetAtt": "AnalyzerRole.Arn"}


def test_bucket_security_retention_and_event_loop_prevention():
    resources = template()["Resources"]
    bucket = resources["InputBucket"]["Properties"]
    assert all(bucket["PublicAccessBlockConfiguration"].values())
    assert bucket["OwnershipControls"]["Rules"] == [{"ObjectOwnership": "BucketOwnerEnforced"}]
    assert (
        bucket["BucketEncryption"]["ServerSideEncryptionConfiguration"][0][
            "ServerSideEncryptionByDefault"
        ]["SSEAlgorithm"]
        == "AES256"
    )
    assert bucket["LifecycleConfiguration"]["Rules"][0]["ExpirationInDays"] == 7
    assert resources["SummaryLogGroup"]["Properties"]["RetentionInDays"] == 14
    rule = bucket["NotificationConfiguration"]["LambdaConfigurations"][0]
    assert rule["Filter"]["S3Key"]["Rules"] == [{"Name": "prefix", "Value": "incoming/"}]
    deny = resources["InputBucketPolicy"]["Properties"]["PolicyDocument"]["Statement"][0]
    assert deny["Effect"] == "Deny"
    assert deny["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}


def test_workflow_has_no_cloud_credentials_or_deploy_permissions():
    workflow = yaml.safe_load(Path(".github/workflows/checks.yml").read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    steps = workflow["jobs"]["checks"]["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    assert steps[-1]["run"] == "python tools/verify.py"
    for step in steps:
        assert "env" not in step
        if "uses" in step:
            assert len(step["uses"].split("@")[1]) == 40


def test_invocation_is_scoped_to_one_bucket_and_account():
    resources = template()["Resources"]
    permission = resources["AnalyzerInvokePermission"]["Properties"]
    assert permission == {
        "Action": "lambda:InvokeFunction",
        "FunctionName": {"Ref": "Analyzer"},
        "Principal": "s3.amazonaws.com",
        "SourceAccount": {"Ref": "AWS::AccountId"},
        "SourceArn": {
            "Sub": "arn:${AWS::Partition}:s3:::${AWS::AccountId}-${AWS::Region}-lad-synthetic-input"
        },
    }
    assert resources["InputBucket"]["DependsOn"] == "AnalyzerInvokePermission"
